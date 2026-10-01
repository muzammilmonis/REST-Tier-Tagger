#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = json.loads((ROOT / "VERSION_MATRIX.json").read_text(encoding="utf-8"))
BRANCHES = {x["branch"]: x for x in MATRIX["branches"]}


def run(cmd, cwd=None):
    print("+", " ".join(map(str, cmd)))
    subprocess.run(cmd, cwd=cwd, check=True)


def collect(repo: Path, branch: str, dist: Path):
    dist.mkdir(parents=True, exist_ok=True)
    jars = []
    for p in repo.rglob("build/libs/*.jar"):
        s = p.as_posix().lower()
        name = p.name.lower()
        if any(x in name for x in ("sources", "javadoc", "dev-shadow", "-dev.jar")):
            continue
        if "/common/build/libs/" in s:
            continue
        loader = "neoforge" if "/neoforge/" in s else "fabric"
        jars.append((p, loader))
    if not jars:
        raise RuntimeError("Build finished but no distributable JARs were found")

    copied = []
    for idx, (src, loader) in enumerate(sorted(jars)):
        # Keep multiple outputs if a branch really emits more than one runtime jar.
        suffix = "" if sum(1 for _, l in jars if l == loader) == 1 else f"-{idx+1}"
        dst = dist / f"REST-Tier-Tagger-{branch}-{loader}{suffix}.jar"
        shutil.copy2(src, dst)
        copied.append(dst)
        print("artifact:", dst)
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
    if repo.exists(): shutil.rmtree(repo)
    if dist.exists(): shutil.rmtree(dist)
    work_root.mkdir(exist_ok=True)

    run(["git", "clone", "--depth", "1", "--branch", upstream_branch,
         "https://github.com/mctiers-dev/TierTagger.git", str(repo)])
    run([sys.executable, str(ROOT / "tools" / "patch_branch.py"), str(repo), "--branch", branch])

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
