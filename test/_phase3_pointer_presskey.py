#!/usr/bin/env python3
"""Compare pressKey / drag-lock / heldButton between upstream and ours."""
from pathlib import Path
import subprocess

repo = Path("/mnt/c/Users/Antho/Projects/frametop-customized-main")
up = Path("/tmp/upstream-ft-pointer.cpp").read_text(encoding="utf-8")
ours = (repo / "pointer/helper/ft-pointer.cpp").read_text(encoding="utf-8")

for label, t in [("UP", up), ("OURS", ours)]:
    print(f"==== {label}")
    for needle in [
        "pressKey",
        "pressPose",
        "heldButton",
        "pressRight",
        "FramePanel",
        "dragDistance",
        'ft_screens", "up"',
        "titleCarry",
        "g_catcher",
    ]:
        print(f"  {needle!r}: {t.count(needle)}")
    print()

# show ours declarations around leftHeld / dragDistance
i = ours.find("bool leftHeld")
print("=== OURS leftHeld decls ===")
print(ours[i : i + 500])

i = up.find("bool leftHeld")
print("\n=== UP leftHeld decls ===")
print(up[i : i + 700])

# show upstream drag-still block with more context for insertion point in ours
i = up.find("if (!pressKey.empty() && leftHeld)")
if i < 0:
    i = up.find("pressKey.clear()")
print("\n=== UP pressKey still block search ===", i)
# find the still block properly
i = up.find("for (int i = 0; still && i < 3; ++i)")
print(up[max(0, i - 400) : i + 1100])

# find similar region in ours (dragging / leftHeld pose update)
for marker in ["pressKey", "dragDistance = lastDistance", "leftHeld &&", "if (leftHeld)"]:
    j = ours.find(marker)
    print(f"\nours marker {marker!r} @ {j}")
