package __BASE_PACKAGE__;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ConcurrentHashMap;

/**
 * REST Tier Tagger bridge.
 *
 * Converts tiers.rest profile responses into the MCTiers-style JSON shape that
 * upstream TierTagger already knows how to render. This keeps the rendering,
 * cache, nametag and player-list code version-native while swapping only the
 * data provider.
 */
public final class RestTiersBridge {
    public static final String REST_BASE = "https://tiers.rest";
    private static final String PLAYER_ENDPOINT = "/api/public/player/";
    private static final long PROFILE_TTL_MS = 60_000L;
    private static final long NAME_TTL_MS = 3_600_000L;

    private static final Map<String, CacheValue> PROFILE_CACHE = new ConcurrentHashMap<>();
    private static final Map<UUID, CacheValue> NAME_CACHE = new ConcurrentHashMap<>();

    private static final String[][] REST_MODES = new String[][] {
            {"vanilla", "Vanilla"},
            {"uhc", "UHC"},
            {"pot", "Pot"},
            {"netherop", "NethOP"},
            {"smp", "SMP"},
            {"sword", "Sword"},
            {"axe", "Axe"},
            {"mace", "Mace"},
            {"spearmace", "SpearMace"},
            {"spearelytra", "SpearElytra"},
            {"minecart", "Minecart"},
            {"modernmace", "ModernMace"}
    };

    private RestTiersBridge() {}

    public static String[][] restModes() {
        String[][] copy = new String[REST_MODES.length][2];
        for (int i = 0; i < REST_MODES.length; i++) {
            copy[i][0] = REST_MODES[i][0];
            copy[i][1] = REST_MODES[i][1];
        }
        return copy;
    }

    public static CompletableFuture<String> fetchProfileJson(HttpClient client, UUID uuid) {
        final String uuidText = uuid.toString();
        return fetchCanonicalProfile(client, uuidText, uuidText, true)
                .exceptionallyCompose(firstFailure -> resolveName(client, uuid).thenCompose(name -> {
                    if (name == null || name.isBlank()) {
                        return CompletableFuture.failedFuture(firstFailure);
                    }
                    return fetchCanonicalProfile(client, name, uuidText, false);
                }));
    }

    public static CompletableFuture<String> fetchRankingsJson(HttpClient client, UUID uuid) {
        return fetchProfileJson(client, uuid).thenApply(profileJson -> {
            JsonObject profile = JsonParser.parseString(profileJson).getAsJsonObject();
            JsonElement rankings = profile.get("rankings");
            return rankings != null && rankings.isJsonObject() ? rankings.toString() : "{}";
        });
    }

    public static CompletableFuture<String> fetchProfileByNameJson(HttpClient client, String query) {
        if (query == null || query.isBlank()) {
            return CompletableFuture.failedFuture(new IllegalArgumentException("player query is blank"));
        }
        return fetchCanonicalProfile(client, query.trim(), null, false);
    }

    public static void clearCache() {
        PROFILE_CACHE.clear();
        NAME_CACHE.clear();
    }

    private static CompletableFuture<String> fetchCanonicalProfile(HttpClient client, String identifier,
                                                                    String preferredUuid, boolean uuidProbe) {
        String cacheKey = identifier.toLowerCase(Locale.ROOT);
        String cached = getCached(PROFILE_CACHE, cacheKey, PROFILE_TTL_MS);
        if (cached != null) {
            return CompletableFuture.completedFuture(cached);
        }

        String url = REST_BASE + PLAYER_ENDPOINT + encode(identifier);
        HttpRequest request = HttpRequest.newBuilder(URI.create(url))
                .timeout(Duration.ofSeconds(8))
                .header("Accept", "application/json")
                .header("User-Agent", "REST-Tier-Tagger/1.0")
                .GET()
                .build();

        return client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
                .thenApply(response -> {
                    if (response.statusCode() < 200 || response.statusCode() >= 300) {
                        throw new CompletionException(new IllegalStateException(
                                "tiers.rest returned HTTP " + response.statusCode() + " for " + identifier));
                    }
                    JsonObject canonical = canonicalize(response.body(), identifier, preferredUuid);
                    // A UUID probe is allowed to fail over to Mojang name resolution when tiers.rest
                    // does not expose UUID lookup. A real empty player profile still has a name.
                    if (uuidProbe && canonical.get("name").getAsString().equals(identifier)
                            && canonical.getAsJsonObject("rankings").size() == 0) {
                        throw new CompletionException(new IllegalStateException("UUID lookup returned no REST profile"));
                    }
                    String result = canonical.toString();
                    putCached(PROFILE_CACHE, cacheKey, result);
                    String name = canonical.get("name").getAsString();
                    if (name != null && !name.isBlank()) {
                        putCached(PROFILE_CACHE, name.toLowerCase(Locale.ROOT), result);
                    }
                    return result;
                });
    }

    private static CompletableFuture<String> resolveName(HttpClient client, UUID uuid) {
        String cached = getCached(NAME_CACHE, uuid, NAME_TTL_MS);
        if (cached != null) {
            return CompletableFuture.completedFuture(cached);
        }

        String compact = uuid.toString().replace("-", "");
        String url = "https://sessionserver.mojang.com/session/minecraft/profile/" + compact;
        HttpRequest request = HttpRequest.newBuilder(URI.create(url))
                .timeout(Duration.ofSeconds(8))
                .header("Accept", "application/json")
                .header("User-Agent", "REST-Tier-Tagger/1.0")
                .GET()
                .build();

        return client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
                .thenApply(response -> {
                    if (response.statusCode() < 200 || response.statusCode() >= 300) {
                        return null;
                    }
                    try {
                        JsonObject obj = JsonParser.parseString(response.body()).getAsJsonObject();
                        JsonElement name = obj.get("name");
                        if (name != null && name.isJsonPrimitive()) {
                            String value = name.getAsString();
                            putCached(NAME_CACHE, uuid, value);
                            return value;
                        }
                    } catch (Exception ignored) {
                    }
                    return null;
                });
    }

    private static JsonObject canonicalize(String rawJson, String requestedName, String preferredUuid) {
        JsonElement parsed = JsonParser.parseString(rawJson);
        JsonObject root = asObject(parsed);
        if (root == null) {
            throw new CompletionException(new IllegalStateException("tiers.rest response is not a JSON object"));
        }

        JsonObject profile = unwrapProfile(root);
        String name = firstText(profile, "name", "username", "playerName", "player");
        if (name == null || name.isBlank()) {
            name = firstText(root, "name", "username", "playerName", "player");
        }
        if (name == null || name.isBlank()) {
            name = requestedName;
        }

        String uuid = firstText(profile, "uuid", "id");
        if (uuid == null || uuid.isBlank() || !looksLikeUuid(uuid)) {
            uuid = firstText(root, "uuid", "id");
        }
        if (uuid == null || uuid.isBlank() || !looksLikeUuid(uuid)) {
            uuid = preferredUuid;
        }
        if (uuid == null || uuid.isBlank() || !looksLikeUuid(uuid)) {
            uuid = UUID.nameUUIDFromBytes(("REST:" + name).getBytes(StandardCharsets.UTF_8)).toString();
        }

        LinkedHashMap<String, String> placements = new LinkedHashMap<>();
        collectKnownContainers(profile, placements);
        if (profile != root) {
            collectKnownContainers(root, placements);
        }
        collectDirectModeEntries(profile, placements);
        if (profile != root) {
            collectDirectModeEntries(root, placements);
        }

        JsonObject rankings = new JsonObject();
        for (Map.Entry<String, String> entry : placements.entrySet()) {
            String mode = normalizeMode(entry.getKey());
            String tier = validTier(entry.getValue());
            if (mode == null || tier == null) {
                continue;
            }
            addRanking(rankings, mode, tier);
            // Compatibility aliases used by different TierTagger generations.
            if ("netherop".equals(mode)) {
                addRanking(rankings, "nethop", tier);
                addRanking(rankings, "neth_pot", tier);
            }
        }

        JsonObject out = new JsonObject();
        out.addProperty("uuid", normalizeUuid(uuid));
        out.addProperty("name", name);
        out.add("rankings", rankings);
        out.addProperty("region", "");
        out.addProperty("points", 0);
        out.addProperty("overall", 0);
        out.add("badges", new JsonArray());
        out.addProperty("combat_master", false);
        return out;
    }

    private static void addRanking(JsonObject rankings, String mode, String tier) {
        if (rankings.has(mode)) {
            return;
        }
        int numeric = tier.charAt(2) - '0';
        int pos = tier.charAt(0) == 'H' ? 0 : 1;
        JsonObject ranking = new JsonObject();
        ranking.addProperty("tier", numeric);
        ranking.addProperty("pos", pos);
        ranking.add("peak_tier", null);
        ranking.add("peak_pos", null);
        ranking.addProperty("attained", 0L);
        ranking.addProperty("retired", false);
        rankings.add(mode, ranking);
    }

    private static JsonObject unwrapProfile(JsonObject root) {
        String[] wrappers = {"profile", "data", "result"};
        for (String key : wrappers) {
            JsonElement value = root.get(key);
            if (value != null && value.isJsonObject()) {
                JsonObject obj = value.getAsJsonObject();
                JsonElement player = obj.get("player");
                if (player != null && player.isJsonObject()) {
                    return player.getAsJsonObject();
                }
                JsonElement profile = obj.get("profile");
                if (profile != null && profile.isJsonObject()) {
                    return profile.getAsJsonObject();
                }
                return obj;
            }
        }
        JsonElement player = root.get("player");
        if (player != null && player.isJsonObject()) {
            return player.getAsJsonObject();
        }
        return root;
    }

    private static void collectKnownContainers(JsonObject obj, Map<String, String> out) {
        String[] keys = {"placements", "rankings", "ranks", "gamemodes", "modes", "tiers", "tierMap"};
        for (String key : keys) {
            JsonElement value = obj.get(key);
            if (value != null) {
                collectPlacements(value, out);
            }
        }
    }

    private static void collectPlacements(JsonElement element, Map<String, String> out) {
        if (element == null || element.isJsonNull()) {
            return;
        }
        if (element.isJsonArray()) {
            for (JsonElement child : element.getAsJsonArray()) {
                if (!child.isJsonObject()) continue;
                JsonObject obj = child.getAsJsonObject();
                String mode = firstText(obj, "modeSlug", "gamemodeSlug", "mode", "gamemode", "id", "slug");
                String tier = firstText(obj, "tier", "rank", "value", "tierName", "placement");
                if (tier == null) {
                    JsonElement rank = obj.get("ranking");
                    if (rank != null && rank.isJsonObject()) {
                        tier = firstText(rank.getAsJsonObject(), "tier", "rank", "value", "tierName", "placement");
                    }
                }
                putPlacement(out, mode, tier);
            }
            return;
        }
        if (!element.isJsonObject()) {
            return;
        }
        JsonObject map = element.getAsJsonObject();
        for (Map.Entry<String, JsonElement> e : map.entrySet()) {
            String mode = e.getKey();
            JsonElement value = e.getValue();
            String tier = null;
            if (value != null && value.isJsonPrimitive()) {
                tier = value.getAsString();
            } else if (value != null && value.isJsonObject()) {
                JsonObject obj = value.getAsJsonObject();
                String embeddedMode = firstText(obj, "modeSlug", "gamemodeSlug", "mode", "gamemode", "id", "slug");
                if (embeddedMode != null) mode = embeddedMode;
                tier = firstText(obj, "tier", "rank", "value", "tierName", "placement");
                if (tier == null) {
                    JsonElement rank = obj.get("ranking");
                    if (rank != null && rank.isJsonObject()) {
                        tier = firstText(rank.getAsJsonObject(), "tier", "rank", "value", "tierName", "placement");
                    }
                }
            }
            putPlacement(out, mode, tier);
        }
    }

    private static void collectDirectModeEntries(JsonObject obj, Map<String, String> out) {
        for (Map.Entry<String, JsonElement> e : obj.entrySet()) {
            String key = e.getKey();
            if (isReservedKey(key)) continue;
            JsonElement value = e.getValue();
            if (value != null && value.isJsonPrimitive() && value.getAsJsonPrimitive().isString()) {
                String tier = validTier(value.getAsString());
                if (tier != null) putPlacement(out, key, tier);
            } else if (value != null && value.isJsonObject()) {
                JsonObject child = value.getAsJsonObject();
                String tier = firstText(child, "tier", "rank", "value", "tierName", "placement");
                if (validTier(tier) != null) putPlacement(out, key, tier);
            }
        }
    }

    private static boolean isReservedKey(String key) {
        String k = key.toLowerCase(Locale.ROOT);
        return k.equals("name") || k.equals("username") || k.equals("player") || k.equals("playername")
                || k.equals("uuid") || k.equals("id") || k.equals("tier") || k.equals("rank")
                || k.equals("profile") || k.equals("data") || k.equals("result") || k.equals("overall")
                || k.equals("region") || k.equals("points") || k.equals("badges") || k.equals("combat_master")
                || k.equals("placements") || k.equals("rankings") || k.equals("ranks") || k.equals("gamemodes")
                || k.equals("modes") || k.equals("tiers") || k.equals("tiermap");
    }

    private static void putPlacement(Map<String, String> out, String mode, String rawTier) {
        String normalizedMode = normalizeMode(mode);
        String tier = validTier(rawTier);
        if (normalizedMode != null && tier != null) {
            out.put(normalizedMode, tier);
        }
    }

    private static String normalizeMode(String raw) {
        if (raw == null) return null;
        String mode = raw.trim().toLowerCase(Locale.ROOT)
                .replace("-", "")
                .replace("_", "")
                .replace(" ", "");
        if (mode.isEmpty()) return null;
        if (mode.equals("nethpot") || mode.equals("nethop") || mode.equals("netheriteop") || mode.equals("netherop")) {
            return "netherop";
        }
        if (mode.equals("crystalpvp") || mode.equals("cpvp")) return "crystal";
        if (mode.equals("macepvp")) return "mace";
        return mode;
    }

    private static String validTier(String raw) {
        if (raw == null) return null;
        String upper = raw.trim().toUpperCase(Locale.ROOT);
        String compact = upper.replaceAll("[^A-Z0-9]", "");
        if (compact.matches("[HL]T[1-5]")) return compact;
        if (compact.matches("HIGH(TIER)?[1-5]")) return "HT" + compact.substring(compact.length() - 1);
        if (compact.matches("LOW(TIER)?[1-5]")) return "LT" + compact.substring(compact.length() - 1);
        return null;
    }

    private static String firstText(JsonObject obj, String... keys) {
        for (String key : keys) {
            JsonElement value = obj.get(key);
            if (value != null && value.isJsonPrimitive()) {
                try {
                    String s = value.getAsString();
                    if (s != null && !s.isBlank()) return s;
                } catch (Exception ignored) {
                }
            }
        }
        return null;
    }

    private static JsonObject asObject(JsonElement element) {
        return element != null && element.isJsonObject() ? element.getAsJsonObject() : null;
    }

    private static boolean looksLikeUuid(String value) {
        if (value == null) return false;
        String compact = value.replace("-", "");
        return compact.matches("[0-9a-fA-F]{32}");
    }

    private static String normalizeUuid(String value) {
        String compact = value.replace("-", "");
        if (compact.length() == 32) {
            return compact.substring(0, 8) + "-" + compact.substring(8, 12) + "-" + compact.substring(12, 16)
                    + "-" + compact.substring(16, 20) + "-" + compact.substring(20);
        }
        return value;
    }

    private static String encode(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8).replace("+", "%20");
    }

    private static <K> String getCached(Map<K, CacheValue> map, K key, long ttlMs) {
        CacheValue value = map.get(key);
        if (value == null) return null;
        if (System.currentTimeMillis() - value.time > ttlMs) {
            map.remove(key);
            return null;
        }
        return value.value;
    }

    private static <K> void putCached(Map<K, CacheValue> map, K key, String value) {
        map.put(key, new CacheValue(value, System.currentTimeMillis()));
    }

    private static final class CacheValue {
        final String value;
        final long time;

        CacheValue(String value, long time) {
            this.value = value;
            this.time = time;
        }
    }
}
