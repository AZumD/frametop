#!/usr/bin/env python3
"""Deep compare held-drag: leave suppression, enter-while-held, lastHit→SteamVR."""
from pathlib import Path
import subprocess

repo = Path("/mnt/c/Users/Antho/Projects/frametop-customized-main")

def show(ref, path):
    return subprocess.check_output(["git", "show", f"{ref}:{path}"], cwd=repo).decode("utf-8", "replace")

ours_ptr = (repo / "pointer/helper/ft-pointer.cpp").read_text(encoding="utf-8", errors="replace")
ours_vr = (repo / "screens/vr.cpp").read_text(encoding="utf-8", errors="replace")
ours_comp = (repo / "screens/compositor.c").read_text(encoding="utf-8", errors="replace")
up_ptr = show("upstream/main", "pointer/helper/ft-pointer.cpp")
up_vr = show("upstream/main", "screens/vr.cpp")
up_comp = show("upstream/main", "screens/compositor.c")

# Extract held-retarget blocks fully
def extract(text, start_marker, n=80):
    i = text.find(start_marker)
    if i < 0:
        return f"MISSING {start_marker}"
    lines = text[i:].splitlines()
    return "\n".join(lines[:n])

print("===== OURS held retarget =====")
print(extract(ours_ptr, "if (leftHeld && !pressKey.empty())", 50))
print("\n===== UP held retarget =====")
print(extract(up_ptr, "if (leftHeld && !pressKey.empty())", 50))

# What happens with lastHit during dragging in ours - does it update overlay hover?
print("\n===== OURS after retarget: lastHit / distance usage =====")
i = ours_ptr.find("if (leftHeld && !pressKey.empty())")
print(ours_ptr[i:i+2500][:2000])

# FT_LEAVE context in both
print("\n===== OURS MouseLeave / FT_LEAVE =====")
i = ours_vr.find("g_press.buttons) return;  // keep KWin pointer")
print(ours_vr[i-400:i+500] if i>=0 else "not found")
print("\n===== UP MouseLeave / FT_LEAVE =====")
i = up_vr.find("g_press.buttons) return;  // keep KWin pointer")
if i < 0:
    i = up_vr.find("keep KWin pointer while a button is held")
print(up_vr[i-400:i+500] if i>=0 else "not found")

# compositor handle_vr_event for leave/enter
print("\n===== OURS compositor FT_LEAVE =====")
for marker in ["FT_LEAVE", "FT_ENTER", "FT_MOTION", "FT_BUTTON"]:
    i = ours_comp.find(f"case {marker}")
    if i < 0:
        i = ours_comp.find(marker)
    print(f"\n-- {marker} @ {i} --")
    print(ours_comp[max(0,i-100):i+600] if i>=0 else "missing")

print("\n===== UP compositor FT_LEAVE =====")
for marker in ["FT_LEAVE", "FT_ENTER", "FT_MOTION", "FT_BUTTON"]:
    i = up_comp.find(f"case {marker}")
    if i < 0:
        i = up_comp.find(marker)
    print(f"\n-- {marker} @ {i} --")
    print(up_comp[max(0,i-100):i+600] if i>=0 else "missing")

# 0a88a6b7 diff against parent for vr.cpp and pointer
print("\n===== 0a88a6b7 --stat =====")
print(subprocess.check_output(["git", "show", "--stat", "--format=%s", "0a88a6b7"], cwd=repo, text=True)[:1500])
