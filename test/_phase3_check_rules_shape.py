#!/usr/bin/env python3
import importlib.util
from pathlib import Path

ROOT = Path("/mnt/c/Users/Antho/Projects/frametop-customized-main")
spec = importlib.util.spec_from_file_location("r", ROOT / "input/input-relay.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
rules = m.read_rules("/tmp/no-such-frametop-input-rules-xyz.json")
print(sorted(rules.keys()))
print(rules.get("key_bindings"))
