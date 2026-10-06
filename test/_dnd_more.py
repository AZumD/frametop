#!/usr/bin/env python3
"""Find remaining DnD gaps vs upstream beyond x+1 enter."""
from pathlib import Path
import subprocess
import difflib

repo = Path("/mnt/c/Users/Antho/Projects/frametop-customized-main")

def show(path):
    return subprocess.check_output(["git", "show", f"upstream/main:{path}"], cwd=repo).decode("utf-8", "replace")

ours_vr = (repo / "screens/vr.cpp").read_text(encoding="utf-8", errors="replace")
up_vr = show("screens/vr.cpp")
ours_c = (repo / "screens/compositor.c").read_text(encoding="utf-8", errors="replace")
up_c = show("screens/compositor.c")
ours_p = (repo / "pointer/helper/ft-pointer.cpp").read_text(encoding="utf-8", errors="replace")
up_p = show("pointer/helper/ft-pointer.cpp")

# Compare panelEvent mouse paths more carefully
def extract(text, start, end_markers, limit=100):
    i = text.find(start)
    if i < 0:
        return f"MISSING {start}"
    lines = text[i:].splitlines()[:limit]
    out = []
    for line in lines:
        out.append(line)
        if any(m in line for m in end_markers) and len(out) > 5:
            # keep going a bit
            pass
        if len(out) >= limit:
            break
    return "\n".join(out)

print("==== OURS panelEvent start ====")
i = ours_vr.find("auto panelEvent")
print(ours_vr[i:i+2200])
print("\n==== UP panelEvent start ====")
i = up_vr.find("auto panelEvent")
print(up_vr[i:i+1800])

# Check if ours converts mouse to seat in a way that breaks float crops
print("\n==== surfaceWidth / outputScale on floats ====")
for label, t in [("OURS", ours_vr), ("UP", up_vr)]:
    print(label, "surfaceWidth", t.count("surfaceWidth"), "outputScale", t.count("outputScale"), "ft_buffer_to_seat", t.count("ft_buffer_to_seat"))

# Does MakePanel set interactive flags for floats the same?
print("\n==== MakePanel ====")
for label, t in [("OURS", ours_vr), ("UP", up_vr)]:
    i = t.find("void MakePanel")
    print(label, t[i:i+900] if i>=0 else "missing")

# Compare Sort order of overlay polling - floats vs screens
print("\n==== g_screens iteration / UpdateCatcher call ====")
for label, t in [("OURS", ours_vr), ("UP", up_vr)]:
    print(label, "UpdateCatcher(); count", t.count("UpdateCatcher()"))
    i = t.find("UpdateCatcher();")
    print(t[max(0,i-200):i+100] if i>=0 else "no call")

# Floating docs about drag proxy
print("\n==== drag proxy mentions ====")
docs = (repo / "docs/floating-windows.md").read_text(encoding="utf-8", errors="replace")
print("drag proxy" in docs)
i = docs.find("drag proxy")
print(docs[max(0,i-100):i+300] if i>=0 else "")

# Check if FT_MOTION for different screen while button held could be blocked by titleCarry incorrectly
print("\n==== titleCarry on non-float? ====")
print("titleCarry floating check in press", "s.floating && e.button" in ours_vr)

# Compositor: does pointer_focus compare work across spare screens?
print("\n==== compositor screen bounds ====")
print("MAX_SCREENS ours", [l for l in ours_c.splitlines() if "MAX_SCREENS" in l][:3])
