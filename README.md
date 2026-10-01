# REST Tier Tagger — 1.20.1 to 26.3 builder

REST Tier Tagger is a `tiers.rest`-powered derivative of MCTiers' TierTagger client mod. It keeps the upstream version-native nametag, TAB/player-list, cache, search/profile and config behaviour while swapping the ranking source to REST Tiers.

## What this pack changes

- REST profile source: `https://tiers.rest/api/public/player/:ign`
- 12 current REST modes: Vanilla, UHC, Pot, NethOP, SMP, Sword, Axe, Mace, SpearMace, SpearElytra, Minecart, ModernMace
- REST-owned private-use icon font included; MCTiers/SubTiers restricted icon bitmaps are removed
- REST icon semantics match the existing RestTierTags/site mapping in `REST_ICON_MAP.json`
- visible mod name: **REST Tier Tagger**
- mod id: `resttiertagger`
- upstream Modrinth update checker disabled
- `/tiertagger <player>` stays unchanged
- `/rtiertagger <player>` is added as an alias with the exact same output/handler

## Supported build targets

The pack intentionally starts at **1.20.1** and ends at **26.3**. It builds the upstream TierTagger branches that exist in that range:

`1.20.1, 1.20.2, 1.20.3, 1.20.6, 1.21, 1.21.2, 1.21.4, 1.21.5, 1.21.6, 1.21.9, 1.21.11, 26.1, 26.2, 26.3`

`1.20.1` uses upstream's `1.20` branch and is labelled/output as `1.20.1`. The builder does not invent unsupported upstream branches for patch releases TierTagger itself does not maintain.

## Commands

```text
/tiertagger <player>
/rtiertagger <player>
```

Both commands use the same TierTagger player search/profile output. The `r` command is only an alias.

## Icons

The builder removes MCTiers/SubTiers private-use assets and installs its own REST icon font. The mode-to-item semantics follow the existing RestTierTags mapping, for example Vanilla/Sword -> diamond-sword style glyph, UHC -> golden-apple style glyph, Pot -> potion style glyph, SMP -> pickaxe style glyph, SpearMace -> trident/spear style glyph, etc. The included glyph bitmaps are original REST pack assets, not copies of MCTiers or Minecraft textures.

## One-click online build

Put this folder in a GitHub repository and run:

**Actions -> Build REST Tier Tagger - 1.20.1 to 26.3 -> Run workflow**

The matrix builds every target and uploads each runtime JAR. The bundle job creates `REST-Tier-Tagger-1.20.1-to-26.3.zip`.

## Local build

Requirements: Git, Python 3, the Java version listed in `VERSION_MATRIX.json`, and Internet access for Gradle/Minecraft dependencies.

```bash
python3 tools/build_one.py 1.21.11
python3 tools/build_all.py
```

Output goes to `dist/<minecraft-version>/`.

## Tier conversion

REST values are converted into TierTagger's normal ranking representation:

- `HT2` -> `tier=2, pos=0`
- `LT2` -> `tier=2, pos=1`

NethOP compatibility aliases are emitted for older TierTagger generations (`netherop`, `nethop`, `neth_pot`).

## Build status

The patcher and helper scripts are statically validated in this environment. Actual Minecraft dependency resolution/compilation requires Internet access, so the included GitHub Actions workflow is the authoritative build path for the JARs. `verify_jars.py` runs after every successful build.
