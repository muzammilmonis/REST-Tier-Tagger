#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = json.loads((ROOT / "VERSION_MATRIX.json").read_text(encoding="utf-8"))
BRANCHES = {x["branch"]: x for x in MATRIX["branches"]}


def run(cmd, cwd=None):
    print("+", " ".join(map(str, cmd)))
    subprocess.run(cmd, cwd=cwd, check=True)


def runtime_loader(path: Path) -> str | None:
    """Return the real loader only for a branded distributable mod jar.

    Modern multiloader builds can emit helper/root jars in build/libs alongside the
    actual Fabric/NeoForge artifacts. Those helper jars are not installable mods and
    do not contain loader metadata, so they must never be published or verified as
    runtime builds.
    """
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())

            if "fabric.mod.json" in names:
                metadata = zf.read("fabric.mod.json").decode("utf-8", errors="replace").lower()
                if "resttiertagger" in metadata or "rest tier tagger" in metadata:
                    return "fabric"
                return None

            for meta in ("META-INF/neoforge.mods.toml", "META-INF/mods.toml"):
                if meta in names:
                    metadata = zf.read(meta).decode("utf-8", errors="replace").lower()
                    if "resttiertagger" in metadata or "rest tier tagger" in metadata:
                        return "neoforge"
                    return None
    except (OSError, zipfile.BadZipFile, KeyError):
        return None

    return None


def collect(repo: Path, branch: str, dist: Path):
    dist.mkdir(parents=True, exist_ok=True)
    jars = []

    for p in repo.rglob("build/libs/*.jar"):
        name = p.name.lower()
        if any(x in name for x in ("sources", "javadoc", "dev-shadow", "-dev.jar")):
            continue

        loader = runtime_loader(p)
        if loader is None:
            print("skip non-runtime/unbranded jar:", p)
            continue
        jars.append((p, loader))

    if not jars:
        raise RuntimeError("Build finished but no branded distributable JARs were found")

    copied = []
    for loader in sorted({loader for _, loader in jars}):
        loader_jars = sorted(p for p, l in jars if l == loader)
        for idx, src in enumerate(loader_jars, start=1):
            suffix = "" if len(loader_jars) == 1 else f"-{idx}"
            dst = dist / f"REST-Tier-Tagger-{branch}-{loader}{suffix}.jar"
            shutil.copy2(src, dst)
            copied.append(dst)
            print("artifact:", dst, "<-", src)

    return copied


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("branch", choices=BRANCHES)
    ap.add_argument("--keep-work", action="store_true")
    args = ap.parse_args()

    branch = args.branch
    upstream_branch = BRANCHES[branch].get("upstream_branch", branch)
    work_root = ROOT / ".work"
    repo = work_root / branch
    dist = ROOT / "dist" / branch
    if repo.exists():
        shutil.rmtree(repo)
    if dist.exists():
        shutil.rmtree(dist)
    work_root.mkdir(exist_ok=True)

    run([
        "git", "clone", "--depth", "1", "--branch", upstream_branch,
        "https://github.com/mctiers-dev/TierTagger.git", str(repo),
    ])
    run([sys.executable, str(ROOT / "tools" / "patch_branch.py"), str(repo), "--branch", branch])

    # Final provider cleanup for modern enum/multiloader branches. This intentionally
    # preserves the upstream settings/profile/search/rendering UI and only removes
    # old provider references/assets that must not ship in the REST build.
    run([sys.executable, str(ROOT / "tools" / "cleanup_upstream_refs.py"), str(repo)])

    gradlew = repo / ("gradlew.bat" if os.name == "nt" else "gradlew")
    if os.name != "nt":
        gradlew.chmod(gradlew.stat().st_mode | 0o111)
    run([str(gradlew), "build", "--no-daemon", "--stacktrace"], cwd=repo)

    artifacts = collect(repo, branch, dist)
    run([sys.executable, str(ROOT / "tools" / "verify_jars.py"), *map(str, artifacts)])

    if not args.keep_work:
        shutil.rmtree(repo, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
