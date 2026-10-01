#!/usr/bin/env python3
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path


def info(msg: str) -> None:
    print(f"[REST Tier Tagger cleanup] {msg}")


def patch_tier_list(repo: Path) -> None:
    candidates = [
        p for p in repo.rglob("TierList.java")
        if "/build/" not in p.as_posix() and "/.gradle/" not in p.as_posix()
    ]
    if not candidates:
        return
    candidates.sort(key=lambda p: (0 if "/common/" in p.as_posix() else 1, len(p.as_posix())))
    path = candidates[0]
    text = path.read_text(encoding="utf-8")

    # Modern TierTagger uses an enum only to populate the Tierlist settings tab.
    # Keep the UI intact, but expose REST Tiers as the sole built-in provider.
    if "public enum TierList" in text:
        m = re.search(
            r'(public\s+enum\s+TierList\s*\{)(.*?)(\n\s*;\s*\n\s*private\s+final\s+String\s+name;)',
            text,
            re.S,
        )
        if m:
            constants = '\n    REST("REST Tiers", "https://tiers.rest", \'\\uE901\')'
            text = text[:m.start(2)] + constants + text[m.end(2):]

    text = text.replace("https://mctiers.com/api", "https://tiers.rest")
    text = text.replace("https://subtiers.net/api", "https://tiers.rest")
    text = text.replace('"MCTiers"', '"REST Tiers"')
    path.write_text(text, encoding="utf-8")
    info(f"REST-only TierList provider: {path.relative_to(repo)}")


def remove_old_assets(repo: Path) -> None:
    removed = 0
    # Remove the original provider texture trees themselves, not just their files.
    # This avoids empty directory entries being packed back into modern multiloader jars.
    for path in sorted(repo.rglob("*"), key=lambda p: len(p.as_posix()), reverse=True):
        if not path.is_dir():
            continue
        if path.name.lower() not in {"mctiers", "subtiers"}:
            continue
        if "textures" not in {part.lower() for part in path.parts}:
            continue
        shutil.rmtree(path, ignore_errors=True)
        removed += 1

    # Provider selector images are also upstream-specific and no longer needed once
    # TierList contains only REST Tiers. The actual settings/profile/search UI stays intact.
    for path in repo.rglob("*"):
        if not path.is_file():
            continue
        s = path.as_posix().lower()
        if "/textures/tierlists/" in s and path.name.lower() in {"mctiers.png", "subtiers.png"}:
            path.unlink(missing_ok=True)
            removed += 1

    if removed:
        info(f"removed {removed} old provider asset trees/files")


def patch_visible_branding(repo: Path) -> None:
    # Preserve all screens/widgets; only change hard-coded visible product naming.
    for path in repo.rglob("*.java"):
        if "/build/" in path.as_posix() or "/.gradle/" in path.as_posix():
            continue
        text = path.read_text(encoding="utf-8")
        new = text.replace('"TierTagger Config"', '"REST Tier Tagger Config"')
        if new != text:
            path.write_text(new, encoding="utf-8")
            info(f"rebranded visible config title: {path.relative_to(repo)}")


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: cleanup_upstream_refs.py <repo>")
    repo = Path(sys.argv[1]).resolve()
    patch_tier_list(repo)
    remove_old_assets(repo)
    patch_visible_branding(repo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
