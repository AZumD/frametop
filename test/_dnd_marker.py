#!/usr/bin/env python3
"""Diff held-drag related pointer sections; check OverlayList / marker / sendPose."""
from pathlib import Path
import subprocess
import difflib

repo = Path("/mnt/c/Users/Antho/Projects/frametop-customized-main")
ours = (repo / "pointer/helper/ft-pointer.cpp").read_text(encoding="utf-8", errors="replace")
up = subprocess.check_output(["git", "show", "upstream/main:pointer/helper/ft-pointer.cpp"], cwd=repo).decode()

# Extract function FramePanel from both - already same
# Compare comment about Across Frametop's panels
for label, t in [("OURS", ours), ("UP", up)]:
    i = t.find("Across Frametop")
    print(f"==== {label} Across comment @ {i}")
    print(t[i:i+500] if i>=0 else "MISSING Across Frametop comment!")

# Check if ours has the drag-lock comment about giving way
print("\n==== OURS drag lock header mentions cross-panel?", "Across Frametop" in ours or "gives way" in ours)

# Marker while dragging
for label, t in [("OURS", ours), ("UP", up)]:
    print(f"\n==== {label} marker/dragging snippets ====")
    for n in ["HideOverlay(marker)", "ShowOverlay(marker)", "onPanel", "dragging"]:
        pass
    # find ShowOverlay(marker)
    idx = 0
    count = 0
    while count < 5:
        i = t.find("marker", idx)
        if i < 0:
            break
        ctx = t[max(0,i-80):i+80]
        if "ShowOverlay" in ctx or "HideOverlay" in ctx:
            print(ctx.replace("\n", " | "))
            print("---")
            count += 1
        idx = i + 1

# Did we deploy rebuilt pointer? Check if FramePanel is in the committed tree vs what's on frame - skip

# Compare compositor handle_vr_event focus change for multi-screen - any difference?
oc = (repo / "screens/compositor.c").read_text(encoding="utf-8", errors="replace")
uc = subprocess.check_output(["git", "show", "upstream/main:screens/compositor.c"], cwd=repo).decode()

def extract_handle(t):
    i = t.find("static void handle_vr_event")
    return t[i:i+2200]

print("\n==== handle_vr_event unified diff (trimmed) ====")
a = extract_handle(oc).splitlines()
b = extract_handle(uc).splitlines()
for line in difflib.unified_diff(a, b, fromfile="ours", tofile="up", lineterm=""):
    if line.startswith("@@") or line.startswith("+") or line.startswith("-"):
        print(line)
