#!/usr/bin/env python3
"""Diagnose cross-panel DnD: compare fork vs upstream held-drag path."""
from pathlib import Path
import subprocess
import re

repo = Path("/mnt/c/Users/Antho/Projects/frametop-customized-main")

def show(ref, path):
    return subprocess.check_output(["git", "show", f"{ref}:{path}"], cwd=repo).decode("utf-8", "replace")

ours_ptr = (repo / "pointer/helper/ft-pointer.cpp").read_text(encoding="utf-8", errors="replace")
ours_vr = (repo / "screens/vr.cpp").read_text(encoding="utf-8", errors="replace")
ours_comp = (repo / "screens/compositor.c").read_text(encoding="utf-8", errors="replace")
up_ptr = show("upstream/main", "pointer/helper/ft-pointer.cpp")
up_vr = show("upstream/main", "screens/vr.cpp")
up_comp = show("upstream/main", "screens/compositor.c")

# Also show 0a88a6b7 if available
for c in ["0a88a6b7", "6122b7eb", "c8fc6351"]:
    try:
        msg = subprocess.check_output(["git", "log", "-1", "--oneline", c], cwd=repo, text=True).strip()
        print(f"commit {msg}")
    except Exception as e:
        print(f"commit {c}: {e}")

def dump(label, text, needles, ctx=200):
    print(f"\n======== {label} ========")
    for n in needles:
        print(f"--- count[{n!r}]={text.count(n)}")
        i = 0
        shown = 0
        while shown < 3:
            j = text.find(n, i)
            if j < 0:
                break
            print(f"@{j}:")
            print(text[max(0, j - ctx): j + ctx + len(n)])
            print("---")
            i = j + 1
            shown += 1

# Pointer: FramePanel, pressKey, held retarget, up
for label, t in [("OURS pointer", ours_ptr), ("UP pointer", up_ptr)]:
    dump(label, t, [
        "bool FramePanel",
        "pressKey",
        "leftHeld && !pressKey.empty()",
        'SendTo(out, "ft_screens", "up")',
        "FT_LEAVE",  # unlikely in pointer
    ], ctx=120)

# VR: leave, catcher, enter while held, g_press
for label, t in [("OURS vr", ours_vr), ("UP vr", up_vr)]:
    dump(label, t, [
        "FT_LEAVE",
        "VREvent_MouseLeave",
        "g_press.buttons",
        "titleCarry",
        "ShowCatcher",
        "Catcher",
        "ReleaseAway",
        'strcmp(cmd, "up")',
        "pointer enter",
        "wlr_seat_pointer_enter",
        "wlr_seat_pointer_notify_enter",
        "ft_vr_pointer",
    ], ctx=180)

# Compositor handle_vr_event for leave/enter
for label, t in [("OURS compositor", ours_comp), ("UP compositor", up_comp)]:
    dump(label, t, [
        "FT_LEAVE",
        "FT_ENTER",
        "FT_MOTION",
        "FT_BUTTON",
        "handle_vr_event",
        "wlr_seat_pointer_notify_enter",
        "wlr_seat_pointer_notify_motion",
        "wlr_seat_pointer_clear_focus",
        "wlr_seat_pointer_notify_button",
    ], ctx=220)
