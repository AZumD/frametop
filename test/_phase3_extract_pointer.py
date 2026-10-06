#!/usr/bin/env python3
"""Extract FramePanel-related regions from upstream/main pointer."""
from pathlib import Path
import subprocess

repo = Path("/mnt/c/Users/Antho/Projects/frametop-customized-main")
up = subprocess.check_output(
    ["git", "show", "upstream/main:pointer/helper/ft-pointer.cpp"],
    cwd=repo,
).decode("utf-8", "replace")
ours = (repo / "pointer/helper/ft-pointer.cpp").read_text(encoding="utf-8", errors="replace")
out = Path("/tmp/upstream-ft-pointer.cpp")
out.write_text(up, encoding="utf-8")
print(f"wrote {out} ({len(up)} bytes)")

# dump FramePanel
i = up.find("bool FramePanel")
print("=== UP FramePanel ===")
print(up[i : i + 800])

# dump leftHeld press with FramePanel
i = up.find("if (FramePanel(lastHit))")
print("\n=== UP FramePanel(lastHit) ===")
print(up[max(0, i - 250) : i + 1400])

# dump hit filter
i = up.find("!FramePanel(key)")
print("\n=== UP hit FramePanel filter ===")
print(up[max(0, i - 350) : i + 900])

# dump releaseLeft
i = up.find("auto releaseLeft")
print("\n=== UP releaseLeft ===")
print(up[i : i + 700])

# ours equivalents
print("\n=== OURS leftHeld press region ===")
i = ours.find("leftHeld = true")
print(ours[max(0, i - 200) : i + 900])

print("\n=== OURS hit loop bestKey ===")
# find collision loop
for marker in ["bestKey", "onEdge", "Intersect"]:
    pass
i = ours.find("lastHit = bestKey")
print(ours[max(0, i - 800) : i + 200])

print("\n=== OURS releaseLeft ===")
i = ours.find("auto releaseLeft")
print(ours[i : i + 500])
