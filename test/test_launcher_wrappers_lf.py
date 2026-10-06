#!/usr/bin/env python3
"""Extensionless Frame launchers must be LF-only (CRLF breaks shebang exec)."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
wrappers = [
    root / "layout" / "ft-layout",
    root / "display-settings" / "ft-display-settings",
    root / "input-settings" / "ft-input-settings",
]
for p in wrappers:
    data = p.read_bytes()
    assert b"\r" not in data, f"{p.relative_to(root)} has CR; fix with test/_fix_crlf_tree.py"
    assert data.startswith(b"#!/"), f"{p.relative_to(root)} missing shebang"
print("ok launcher wrappers LF")
