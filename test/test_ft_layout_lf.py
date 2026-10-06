#!/usr/bin/env python3
"""layout/ft-layout must be LF-only; CRLF breaks shebang exec on the Frame."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
wrapper = root / "layout" / "ft-layout"
data = wrapper.read_bytes()
assert b"\r" not in data, "layout/ft-layout has CR; fix with test/_fix_crlf_tree.py / .gitattributes"
assert data.startswith(b"#!/"), "layout/ft-layout missing shebang"
print("ok ft-layout LF")
