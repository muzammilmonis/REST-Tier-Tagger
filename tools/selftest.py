#!/usr/bin/env python3
"""Cheap sanity tests for the source patcher's brace replacement logic."""
from pathlib import Path
import importlib.util, tempfile
spec=importlib.util.spec_from_file_location("patch", Path(__file__).with_name("patch_branch.py"))
p=importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
source='''package x.model;\npublic class PlayerInfo {\n public static CompletableFuture<PlayerInfo> get(HttpClient client, UUID uuid) { if(true){return null;} return null; }\n}\n'''
out, changed=p.replace_method(source, r"public\s+static\s+CompletableFuture\s*<\s*PlayerInfo\s*>\s+get\s*\([^)]*UUID\s+uuid[^)]*\)\s*\{", "return null;", True)
assert changed and "if(true)" not in out and "return null;" in out
print("patcher self-test OK")
