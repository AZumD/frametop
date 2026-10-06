#!/usr/bin/env python3
"""Check how often float panel transforms might invalidate pressKey (0.001 threshold)."""
from pathlib import Path
repo = Path("/mnt/c/Users/Antho/Projects/frametop-customized-main")
vr = (repo / "screens/vr.cpp").read_text(encoding="utf-8", errors="replace")
# Find UpdateVisibility / soft follow for floating
for needle in ["s.floating", "floating)", "PlaceChrome(s)", "SetAbsolute(s", "SoftFollow", "follow"]:
    print(needle, vr.count(needle))

# soft-follow / arrange applying to floats?
i = vr.find("if (s.floating)")
print("\n--- floating visibility ---")
print(vr[i:i+400])

# Does UpdateArrange skip floats?
i = vr.find("void UpdateArrange")
print("\n--- UpdateArrange head ---")
print(vr[i:i+1200] if i>=0 else "missing")
