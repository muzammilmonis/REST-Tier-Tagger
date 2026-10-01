#!/usr/bin/env python3
from __future__ import annotations
import sys, zipfile
from pathlib import Path

BAD_PATH_BITS = ("/mctiers/", "/subtiers/", "com/thiccindustries/debugger")
BAD_BYTES = (b"https://mctiers.com/api", b"https://api.uku3lig.net/tiers")

def verify(path: Path):
    errors=[]
    with zipfile.ZipFile(path) as z:
        names=z.namelist()
        for n in names:
            low=("/"+n.lower())
            if any(x in low for x in BAD_PATH_BITS):
                errors.append(f"restricted/unwanted path: {n}")
        for n in names:
            if not n.endswith((".class", ".json", ".toml", ".properties")):
                continue
            try: data=z.read(n)
            except Exception: continue
            for needle in BAD_BYTES:
                if needle in data:
                    errors.append(f"old API string in {n}: {needle.decode()}")
        # Branding must be visible in at least one metadata payload.
        meta=b""
        for n in names:
            if n.endswith("fabric.mod.json") or n.endswith("neoforge.mods.toml") or n.endswith("mods.toml"):
                meta += z.read(n)
        if b"REST Tier Tagger" not in meta and b"resttiertagger" not in meta:
            errors.append("REST metadata branding not found")
    if errors:
        raise SystemExit(f"{path}: verification failed:\n  " + "\n  ".join(errors))
    print(f"OK: {path}")

for arg in sys.argv[1:]: verify(Path(arg))
