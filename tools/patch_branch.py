#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE_TEMPLATE = (ROOT / "templates" / "RestTiersBridge.java.tpl").read_text(encoding="utf-8")


def info(msg: str) -> None:
    print(f"[REST Tier Tagger] {msg}")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def package_of(text: str) -> str:
    m = re.search(r"(?m)^\s*package\s+([\w.]+)\s*;", text)
    if not m:
        raise RuntimeError("Could not determine Java package")
    return m.group(1)


def add_import(text: str, fqcn: str) -> str:
    line = f"import {fqcn};"
    if line in text:
        return text
    m = re.search(r"(?m)^\s*package\s+[\w.]+\s*;\s*$", text)
    if not m:
        raise RuntimeError(f"No package declaration while adding {line}")
    return text[:m.end()] + "\n\n" + line + text[m.end():]


def method_span(text: str, signature_regex: str):
    m = re.search(signature_regex, text, re.S)
    if not m:
        return None
    open_brace = text.find("{", m.start(), m.end() + 2)
    if open_brace < 0:
        open_brace = text.find("{", m.end())
    if open_brace < 0:
        raise RuntimeError("Method opening brace not found")
    depth = 0
    in_str = False
    in_chr = False
    esc = False
    line_comment = False
    block_comment = False
    i = open_brace
    while i < len(text):
        c = text[i]
        n = text[i + 1] if i + 1 < len(text) else ""
        if line_comment:
            if c == "\n": line_comment = False
        elif block_comment:
            if c == "*" and n == "/":
                block_comment = False
                i += 1
        elif in_str:
            if esc: esc = False
            elif c == "\\": esc = True
            elif c == '"': in_str = False
        elif in_chr:
            if esc: esc = False
            elif c == "\\": esc = True
            elif c == "'": in_chr = False
        else:
            if c == "/" and n == "/":
                line_comment = True; i += 1
            elif c == "/" and n == "*":
                block_comment = True; i += 1
            elif c == '"': in_str = True
            elif c == "'": in_chr = True
            elif c == "{": depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return open_brace, i
        i += 1
    raise RuntimeError("Unbalanced Java braces")


def replace_method(text: str, signature_regex: str, body: str, required: bool = False) -> tuple[str, bool]:
    span = method_span(text, signature_regex)
    if span is None:
        if required:
            raise RuntimeError(f"Required method not found: {signature_regex}")
        return text, False
    a, b = span
    indent = "        "
    formatted = "{\n" + "\n".join(indent + line if line else "" for line in body.strip().splitlines()) + "\n    }"
    return text[:a] + formatted + text[b + 1:], True


def find_unique(root: Path, name: str) -> Path | None:
    matches = [p for p in root.rglob(name) if "/build/" not in p.as_posix() and "/.gradle/" not in p.as_posix()]
    if not matches:
        return None
    # Prefer common module when multiloader, then src/main.
    matches.sort(key=lambda p: (0 if "/common/" in p.as_posix() else 1, len(p.as_posix())))
    return matches[0]


def patch_player_info(repo: Path, base_package: str) -> None:
    path = find_unique(repo, "PlayerInfo.java")
    if not path:
        raise RuntimeError("PlayerInfo.java not found")
    text = read(path)
    text = add_import(text, f"{base_package}.RestTiersBridge")
    if "import com.google.gson.Gson;" not in text:
        text = add_import(text, "com.google.gson.Gson")

    get_body = """
return RestTiersBridge.fetchProfileJson(client, uuid)
        .thenApply(s -> new Gson().fromJson(s, PlayerInfo.class))
        .whenComplete((info, t) -> {
            if (t != null) TierTagger.getLogger().warn("Error getting REST tier info ({})", uuid, t);
        });
"""
    text, changed_get = replace_method(
        text,
        r"public\s+static\s+CompletableFuture\s*<\s*PlayerInfo\s*>\s+get\s*\([^)]*UUID\s+uuid[^)]*\)\s*\{",
        get_body,
        required=True,
    )

    search_body = """
return RestTiersBridge.fetchProfileByNameJson(client, query)
        .thenApply(s -> new Gson().fromJson(s, PlayerInfo.class))
        .whenComplete((info, t) -> {
            if (t != null) TierTagger.getLogger().warn("Error searching REST tiers player {}", query, t);
        });
"""
    text, _ = replace_method(
        text,
        r"public\s+static\s+CompletableFuture\s*<\s*PlayerInfo\s*>\s+search\s*\([^)]*String\s+query[^)]*\)\s*\{",
        search_body,
        required=True,
    )

    rankings_body = """
return RestTiersBridge.fetchRankingsJson(client, uuid)
        .thenApply(s -> new Gson().fromJson(s, new TypeToken<Map<String, Ranking>>() {}))
        .whenComplete((rankings, t) -> {
            if (t != null) TierTagger.getLogger().warn("Error getting REST player rankings ({})", uuid, t);
        });
"""
    text, rankings_changed = replace_method(
        text,
        r"public\s+static\s+CompletableFuture\s*<\s*Map\s*<\s*String\s*,\s*Ranking\s*>\s*>\s+getRankings\s*\([^)]*UUID\s+uuid[^)]*\)\s*\{",
        rankings_body,
        required=False,
    )
    if rankings_changed and "import com.google.gson.reflect.TypeToken;" not in text:
        text = add_import(text, "com.google.gson.reflect.TypeToken")
    write(path, text)
    info(f"patched REST profile provider: {path.relative_to(repo)}")


def patch_tier_list(repo: Path) -> None:
    path = find_unique(repo, "TierList.java")
    if not path:
        return
    text = read(path)
    if "import com.google.gson.Gson;" not in text:
        text = add_import(text, "com.google.gson.Gson")
    body = r'''
String emptyList = "{\"players\":[],\"unknown\":[],\"fetch_unknown\":true}";
return CompletableFuture.completedFuture(new Gson().fromJson(emptyList, TierList.class));
'''
    text, changed = replace_method(
        text,
        r"public\s+static\s+CompletableFuture\s*<\s*TierList\s*>\s+get\s*\([^)]*\)\s*\{",
        body,
        required=False,
    )
    if changed:
        write(path, text)
        info(f"disabled old /all bootstrap (lazy REST fetch instead): {path.relative_to(repo)}")


def patch_game_modes(repo: Path, base_package: str) -> None:
    path = find_unique(repo, "GameMode.java")
    if not path:
        return
    text = read(path)
    text, static_changed = patch_static_game_mode_enum(text)
    if static_changed:
        info(f"updated static REST mode enum/icons: {path.relative_to(repo)}")
    if "fetchGamemodes" in text:
        text = add_import(text, f"{base_package}.RestTiersBridge")
        if "import java.util.ArrayList;" not in text:
            text = add_import(text, "java.util.ArrayList")
        body = """
List<GameMode> modes = new ArrayList<>();
for (String[] mode : RestTiersBridge.restModes()) {
    modes.add(new GameMode(mode[0], mode[1]));
}
return CompletableFuture.completedFuture(modes);
"""
        text, changed = replace_method(
            text,
            r"public\s+static\s+CompletableFuture\s*<\s*List\s*<\s*GameMode\s*>\s*>\s+fetchGamemodes\s*\([^)]*\)\s*\{",
            body,
            required=False,
        )
        if changed:
            info(f"replaced MCTiers mode list with REST mode list: {path.relative_to(repo)}")
    # Use REST-owned glyphs matching the tiers.rest mode/item mapping.
    if "iconAndColor" in text:
        if "it.unimi.dsi.fastutil.Pair" in text:
            body = """
return switch (this.id) {
    case "vanilla" -> Pair.of('\uE901', TextColor.fromLegacyFormat(ChatFormatting.LIGHT_PURPLE));
    case "uhc" -> Pair.of('\uE902', TextColor.fromLegacyFormat(ChatFormatting.GOLD));
    case "pot" -> Pair.of('\uE903', TextColor.fromRgb(0xff5555));
    case "netherop", "nethop", "neth_pot" -> Pair.of('\uE904', TextColor.fromRgb(0x7d4a40));
    case "smp" -> Pair.of('\uE905', TextColor.fromLegacyFormat(ChatFormatting.AQUA));
    case "sword" -> Pair.of('\uE906', TextColor.fromRgb(0xa4fdf0));
    case "axe" -> Pair.of('\uE907', TextColor.fromLegacyFormat(ChatFormatting.GREEN));
    case "mace" -> Pair.of('\uE908', TextColor.fromLegacyFormat(ChatFormatting.GRAY));
    case "spearmace" -> Pair.of('\uE909', TextColor.fromRgb(0x55aaaa));
    case "spearelytra" -> Pair.of('\uE90A', TextColor.fromRgb(0xaaaaff));
    case "minecart" -> Pair.of('\uE90B', TextColor.fromLegacyFormat(ChatFormatting.RED));
    case "modernmace" -> Pair.of('\uE90C', TextColor.fromLegacyFormat(ChatFormatting.GOLD));
    default -> Pair.of('•', TextColor.fromLegacyFormat(ChatFormatting.WHITE));
};
"""
        elif "net.minecraft.util.Pair" in text:
            body = """
return switch (this.id) {
    case "vanilla" -> new Pair<>('\uE901', TextColor.fromFormatting(Formatting.LIGHT_PURPLE));
    case "uhc" -> new Pair<>('\uE902', TextColor.fromFormatting(Formatting.GOLD));
    case "pot" -> new Pair<>('\uE903', TextColor.fromRgb(0xff5555));
    case "netherop", "nethop", "neth_pot" -> new Pair<>('\uE904', TextColor.fromRgb(0x7d4a40));
    case "smp" -> new Pair<>('\uE905', TextColor.fromFormatting(Formatting.AQUA));
    case "sword" -> new Pair<>('\uE906', TextColor.fromRgb(0xa4fdf0));
    case "axe" -> new Pair<>('\uE907', TextColor.fromFormatting(Formatting.GREEN));
    case "mace" -> new Pair<>('\uE908', TextColor.fromFormatting(Formatting.GRAY));
    case "spearmace" -> new Pair<>('\uE909', TextColor.fromRgb(0x55aaaa));
    case "spearelytra" -> new Pair<>('\uE90A', TextColor.fromRgb(0xaaaaff));
    case "minecart" -> new Pair<>('\uE90B', TextColor.fromFormatting(Formatting.RED));
    case "modernmace" -> new Pair<>('\uE90C', TextColor.fromFormatting(Formatting.GOLD));
    default -> new Pair<>('•', TextColor.fromFormatting(Formatting.WHITE));
};
"""
        else:
            body = None
        if body:
            text, _ = replace_method(
                text,
                r"private\s+Pair\s*<\s*Character\s*,\s*TextColor\s*>\s+iconAndColor\s*\(\s*\)\s*\{",
                body,
                required=False,
            )
    write(path, text)



def patch_commands(repo: Path) -> None:
    """Keep upstream /tiertagger and add /rtiertagger as an exact alias."""
    changed_files = 0
    for path in repo.rglob("*.java"):
        if "/build/" in path.as_posix():
            continue
        text = read(path)
        if "ClientCommandRegistrationCallback.EVENT.register" not in text:
            continue
        text = text.replace('literal(MOD_ID)', 'literal("tiertagger")')
        text = text.replace('literal(TierTagger.MOD_ID)', 'literal("tiertagger")')
        if 'literal("rtiertagger")' in text:
            write(path, text)
            continue

        needle = "ClientCommandRegistrationCallback.EVENT.register"
        pos = 0
        additions = []
        while True:
            start = text.find(needle, pos)
            if start < 0:
                break
            paren = brace = 0
            in_str = in_chr = esc = False
            i = start
            end = None
            while i < len(text):
                c = text[i]
                if in_str:
                    if esc:
                        esc = False
                    elif c == "\\":
                        esc = True
                    elif c == '"':
                        in_str = False
                elif in_chr:
                    if esc:
                        esc = False
                    elif c == "\\":
                        esc = True
                    elif c == "'":
                        in_chr = False
                else:
                    if c == '"':
                        in_str = True
                    elif c == "'":
                        in_chr = True
                    elif c == '(':
                        paren += 1
                    elif c == ')':
                        paren -= 1
                    elif c == '{':
                        brace += 1
                    elif c == '}':
                        brace -= 1
                    elif c == ';' and paren == 0 and brace == 0:
                        end = i + 1
                        break
                i += 1
            if end is None:
                break
            stmt = text[start:end]
            if 'literal("tiertagger")' in stmt:
                alias = stmt.replace('literal("tiertagger")', 'literal("rtiertagger")', 1)
                additions.append((end, "\n\n        " + alias))
            pos = end
        for end, alias in reversed(additions):
            text = text[:end] + alias + text[end:]
        if additions or 'literal("tiertagger")' in text:
            write(path, text)
            changed_files += 1
    if changed_files:
        info(f"preserved /tiertagger and added /rtiertagger alias in {changed_files} command source file(s)")


def patch_static_game_mode_enum(text: str) -> tuple[str, bool]:
    if "public enum GameMode" not in text or "private final String icon;" not in text:
        return text, False
    m = re.search(r'(public\s+enum\s+GameMode[^\{]*\{)(.*?)(\n\s*;\s*\n\s*private\s+final\s+int\s+id;)', text, re.S)
    if not m:
        return text, False
    constants = """
    VANILLA(0, "Vanilla", "vanilla", "\\uE901", TextColor.fromFormatting(Formatting.LIGHT_PURPLE)),
    UHC(1, "UHC", "uhc", "\\uE902", TextColor.fromFormatting(Formatting.GOLD)),
    POT(2, "Pot", "pot", "\\uE903", TextColor.fromRgb(0xff5555)),
    NETH_POT(3, "NethOP", "netherop", "\\uE904", TextColor.fromRgb(0x7d4a40)),
    SMP(4, "SMP", "smp", "\\uE905", TextColor.fromRgb(0x55ffff)),
    SWORD(5, "Sword", "sword", "\\uE906", TextColor.fromRgb(0xa4fdf0)),
    AXE(6, "Axe", "axe", "\\uE907", TextColor.fromFormatting(Formatting.GREEN)),
    MACE(7, "Mace", "mace", "\\uE908", TextColor.fromFormatting(Formatting.GRAY)),
    SPEAR_MACE(8, "SpearMace", "spearmace", "\\uE909", TextColor.fromRgb(0x55aaaa)),
    SPEAR_ELYTRA(9, "SpearElytra", "spearelytra", "\\uE90A", TextColor.fromRgb(0xaaaaff)),
    MINECART(10, "Minecart", "minecart", "\\uE90B", TextColor.fromFormatting(Formatting.RED)),
    MODERN_MACE(11, "ModernMace", "modernmace", "\\uE90C", TextColor.fromFormatting(Formatting.GOLD))"""
    return text[:m.start(2)] + "\n" + constants + text[m.end(2):], True


def install_rest_icons(repo: Path) -> None:
    src_assets = ROOT / "assets" / "rest-icons"
    if not src_assets.exists():
        raise RuntimeError("REST icon assets directory missing")
    candidates = [repo / "common" / "src" / "main" / "resources", repo / "src" / "main" / "resources"]
    resource_root = next((x for x in candidates if x.exists()), candidates[-1])
    icon_dest = resource_root / "assets" / "resttiertagger" / "textures" / "icons"
    icon_dest.mkdir(parents=True, exist_ok=True)
    for png in src_assets.glob("*.png"):
        shutil.copy2(png, icon_dest / png.name)

    glyphs = [
        ("vanilla", "\ue901"), ("uhc", "\ue902"), ("pot", "\ue903"),
        ("netherop", "\ue904"), ("smp", "\ue905"), ("sword", "\ue906"),
        ("axe", "\ue907"), ("mace", "\ue908"), ("spearmace", "\ue909"),
        ("spearelytra", "\ue90a"), ("minecart", "\ue90b"), ("modernmace", "\ue90c"),
    ]
    providers = []
    for name, glyph in glyphs:
        providers.append({"type": "bitmap", "file": f"resttiertagger:icons/{name}.png", "ascent": 8, "height": 8, "chars": [glyph]})
    font = resource_root / "assets" / "minecraft" / "font" / "default.json"
    font.parent.mkdir(parents=True, exist_ok=True)
    write(font, json.dumps({"providers": providers}, ensure_ascii=False, indent=2) + "\n")
    info(f"installed REST-owned mode icon font: {font.relative_to(repo)}")

def patch_config(repo: Path) -> None:
    path = find_unique(repo, "TierTaggerConfig.java")
    if not path:
        return
    text = read(path)
    text = re.sub(r'(private\s+boolean\s+showIcons\s*=\s*)false(\s*;)', r'\1true\2', text)
    text = text.replace("https://mctiers.com/api", "https://tiers.rest")
    text = text.replace("https://api.uku3lig.net/tiers", "https://tiers.rest")
    # Old clients call this mode neth_pot/nethop. Bridge emits aliases, but expose REST's name where possible.
    text = text.replace('"neth_pot"', '"netherop"')
    write(path, text)


def disable_upstream_updates(repo: Path) -> None:
    for path in repo.rglob("TierTagger.java"):
        if "/build/" in path.as_posix():
            continue
        text = read(path)
        text = text.replace("checkForUpdates();", "/* REST fork: upstream Modrinth update checker disabled. */")
        text = re.sub(r'public\s+static\s+final\s+String\s+MOD_ID\s*=\s*"tiertagger"\s*;',
                      'public static final String MOD_ID = "resttiertagger";', text)
        write(path, text)


def remove_title_screen_mixin(repo: Path) -> None:
    for path in repo.rglob("*.mixins.json"):
        try:
            data = json.loads(read(path))
        except Exception:
            continue
        changed = False
        for key in ("mixins", "client"):
            arr = data.get(key)
            if isinstance(arr, list):
                new = [x for x in arr if "TitleScreen" not in str(x)]
                if new != arr:
                    data[key] = new
                    changed = True
        if changed:
            write(path, json.dumps(data, indent=2) + "\n")
            info(f"removed upstream title/update branding mixin: {path.relative_to(repo)}")


def remove_restricted_assets(repo: Path) -> None:
    removed = 0
    for p in list(repo.rglob("*")):
        if not p.is_file():
            continue
        s = p.as_posix().lower()
        if "/build/" in s:
            continue
        if "/mctiers/" in s or "/subtiers/" in s:
            p.unlink(); removed += 1
            continue
        if s.endswith("/assets/minecraft/font/default.json"):
            try:
                t = read(p).lower()
            except Exception:
                t = ""
            if "tiertagger:mctiers" in t or "tiertagger:subtiers" in t:
                p.unlink(); removed += 1
    if removed:
        info(f"removed {removed} upstream restricted icon/font assets")


def patch_fabric_metadata(repo: Path) -> None:
    for path in repo.rglob("fabric.mod.json"):
        try:
            data = json.loads(read(path))
        except Exception:
            continue
        data["id"] = "resttiertagger"
        data["name"] = "REST Tier Tagger"
        data["description"] = "Displays REST Tiers rankings beside Minecraft player names. Powered by tiers.rest."
        authors = data.get("authors")
        if isinstance(authors, list):
            data["authors"] = ["REST Studio", "TierTagger upstream contributors"]
        else:
            data["authors"] = ["REST Studio", "TierTagger upstream contributors"]
        data.pop("icon", None)
        contact = data.get("contact") if isinstance(data.get("contact"), dict) else {}
        contact["homepage"] = "https://tiers.rest"
        data["contact"] = contact
        write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        info(f"rebranded Fabric metadata: {path.relative_to(repo)}")


def patch_text_metadata(repo: Path) -> None:
    # NeoForge/Forge metadata and build properties. Avoid Java source here.
    for path in repo.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".toml", ".properties", ".gradle", ".kts"}:
            continue
        if "/build/" in path.as_posix():
            continue
        try:
            text = read(path)
        except UnicodeDecodeError:
            continue
        original = text
        text = re.sub(r'(?m)^(\s*mod_id\s*=\s*)tiertagger\s*$', r'\1resttiertagger', text)
        text = re.sub(r'(?m)^(\s*archives_base_name\s*=\s*)tiertagger\s*$', r'\1rest-tier-tagger', text)
        text = text.replace('modId="tiertagger"', 'modId="resttiertagger"')
        text = text.replace("modId = \"tiertagger\"", "modId = \"resttiertagger\"")
        text = text.replace('displayName="TierTagger"', 'displayName="REST Tier Tagger"')
        text = text.replace("displayName = \"TierTagger\"", "displayName = \"REST Tier Tagger\"")
        text = text.replace("[[dependencies.tiertagger]]", "[[dependencies.resttiertagger]]")
        text = text.replace('[[dependencies."tiertagger"]]', '[[dependencies."resttiertagger"]]')
        text = re.sub(r'(?m)^\s*iconFile\s*=.*\n?', '', text)
        text = re.sub(r'(?m)^\s*authors\s*=\s*"[^"]*"\s*$', 'authors = "REST Studio; TierTagger upstream contributors"', text)
        text = re.sub(r'(?m)^\s*description\s*=\s*"Display player[^\n]*$', 'description = "Displays REST Tiers rankings beside Minecraft player names. Powered by tiers.rest."', text)
        text = re.sub(r'(?m)^\s*displayURL\s*=\s*"[^"]*"\s*$', 'displayURL = "https://tiers.rest"', text)
        if text != original:
            write(path, text)


def patch_language_values(repo: Path) -> None:
    for path in repo.rglob("*.json"):
        if "/lang/" not in path.as_posix().replace("\\", "/"):
            continue
        try:
            data = json.loads(read(path))
        except Exception:
            continue
        changed = False
        for k, v in list(data.items()):
            if isinstance(v, str) and "TierTagger" in v:
                data[k] = v.replace("TierTagger", "REST Tier Tagger")
                changed = True
        if changed:
            write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def add_notice(repo: Path, branch: str) -> None:
    notice = f"""# REST Tier Tagger derivative notice\n\nThis build is derived from the `mctiers-dev/TierTagger` **{branch}** branch.\n\nChanges made by REST Studio's build layer:\n- ranking source changed from MCTiers to `https://tiers.rest`;\n- mod display name/id changed to REST Tier Tagger / `resttiertagger`;\n- upstream Modrinth update check disabled;\n- MCTiers/SubTiers restricted icon assets are not redistributed;\n- REST mode list and compatibility aliases are used;\n- upstream rendering/cache/UI code is otherwise preserved as far as the branch permits.\n\nThe upstream LICENSE file is intentionally preserved. Review it before distribution.\n"""
    write(repo / "NOTICE-REST.md", notice)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", type=Path)
    ap.add_argument("--branch", default="unknown")
    args = ap.parse_args()
    repo = args.repo.resolve()

    tier_tagger = find_unique(repo, "TierTagger.java")
    player_info = find_unique(repo, "PlayerInfo.java")
    if not tier_tagger or not player_info:
        raise SystemExit("This does not look like a supported TierTagger source tree")

    base_package = package_of(read(tier_tagger))
    bridge_path = tier_tagger.parent / "RestTiersBridge.java"
    write(bridge_path, BRIDGE_TEMPLATE.replace("__BASE_PACKAGE__", base_package))
    info(f"added REST API bridge: {bridge_path.relative_to(repo)}")

    patch_player_info(repo, base_package)
    patch_tier_list(repo)
    patch_game_modes(repo, base_package)
    patch_config(repo)
    patch_commands(repo)
    disable_upstream_updates(repo)
    remove_title_screen_mixin(repo)
    remove_restricted_assets(repo)
    install_rest_icons(repo)
    patch_fabric_metadata(repo)
    patch_text_metadata(repo)
    patch_language_values(repo)
    add_notice(repo, args.branch)

    # Sanity scan: active source should no longer call the old tier APIs.
    bad = []
    needles = ["mctiers.com/api", "api.uku3lig.net/tiers"]
    for p in repo.rglob("*.java"):
        if "/build/" in p.as_posix():
            continue
        t = read(p)
        for n in needles:
            if n in t:
                bad.append(f"{p.relative_to(repo)} contains {n}")
    if bad:
        info("warning: old API strings remain:\n  " + "\n  ".join(bad))

    info(f"branch {args.branch} patched successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
