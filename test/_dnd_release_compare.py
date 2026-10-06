#!/usr/bin/env python3
"""Compare button-up / ReleaseAway / up cmd between upstream and ours."""
from pathlib import Path
import subprocess

repo = Path("/mnt/c/Users/Antho/Projects/frametop-customized-main")
up = subprocess.check_output(["git", "show", "upstream/main:screens/vr.cpp"], text=True, cwd=repo)
ours = (repo / "screens/vr.cpp").read_text(encoding="utf-8", errors="replace")
up_c = subprocess.check_output(["git", "show", "upstream/main:screens/compositor.c"], text=True, cwd=repo)
ours_c = (repo / "screens/compositor.c").read_text(encoding="utf-8", errors="replace")

def chunk(t, start, n=1200):
    i = t.find(start)
    return (t[i:i+n] if i >= 0 else f"MISSING {start}")

for label, t in [("UP", up), ("OURS", ours)]:
    print(f"\n======== {label} ReleaseAway ========")
    print(chunk(t, "void ReleaseAway(", 800))
    print(f"\n======== {label} up command ========")
    print(chunk(t, 'strcmp(cmd, "up")', 400))
    print(f"\n======== {label} MouseButtonUp in panelEvent ========")
    # find panelEvent button handling
    i = t.find("case vr::VREvent_MouseButtonDown:")
    if i < 0:
        i = t.find("VREvent_MouseButtonDown")
    print(chunk(t, "VREvent_MouseButtonDown", 1500))

print("\n======== UP compositor FT_BUTTON ========")
print(chunk(up_c, "case FT_MOTION:", 900))
print("\n======== OURS compositor FT_BUTTON ========")
print(chunk(ours_c, "case FT_MOTION:", 900))
