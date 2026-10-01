#!/usr/bin/env python3
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
m = json.loads((ROOT / "VERSION_MATRIX.json").read_text())
failed = []
for item in m["branches"]:
    b = item["branch"]
    try:
        subprocess.run([sys.executable, str(ROOT / "tools/build_one.py"), b], check=True)
    except subprocess.CalledProcessError:
        failed.append(b)
if failed:
    print("FAILED:", ", ".join(failed), file=sys.stderr)
    raise SystemExit(1)
print("All REST Tier Tagger branches built successfully.")
