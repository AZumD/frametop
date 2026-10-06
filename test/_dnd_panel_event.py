#!/usr/bin/env python3
"""Compare panelEvent mouse path, ToBuffer/crop, Screen::All, visible floats."""
from pathlib import Path
import subprocess

repo = Path("/mnt/c/Users/Antho/Projects/frametop-customized-main")

def show(ref, path):
    return subprocess.check_output(["git", "show", f"{ref}:{path}"], cwd=repo).decode("utf-8", "replace")

ours = (repo / "screens/vr.cpp").read_text(encoding="utf-8", errors="replace")
up = show("upstream/main", "screens/vr.cpp")
docs_up = show("upstream/main", "docs/floating-windows.md")
docs_ours = (repo / "docs/floating-windows.md").read_text(encoding="utf-8", errors="replace")

def section(text, needle, before=200, after=900):
    i = text.find(needle)
    if i < 0:
        return f"MISSING {needle!r}"
    return text[max(0, i - before): i + after]

for label, t in [("OURS", ours), ("UP", up)]:
    print(f"\n======== {label} ToBuffer ========")
    print(section(t, "ToBuffer", 50, 700))
    print(f"\n======== {label} All() ========")
    print(section(t, "All()", 50, 400))
    print(f"\n======== {label} panelEvent MouseMove ========")
    # find panelEvent or MouseMove with g_press
    i = t.find("if (g_press.buttons) g_press.screen")
    if i < 0:
        i = t.find("g_press.screen = index")
    print(t[max(0,i-800):i+900] if i>=0 else "missing g_press.screen update")
    print(f"\n======== {label} floating visible ========")
    print(section(t, "if (s.floating) visible", 80, 200))

print("\n======== UP docs drag section ========")
for needle in ["Crossing", "drag", "between", "FramePanel", "3D mouse"]:
    idx = 0
    while True:
        i = docs_up.lower().find(needle.lower(), idx)
        if i < 0:
            break
        if needle.lower() in ("drag", "between") and "panel" not in docs_up[max(0,i-80):i+120].lower():
            idx = i + 1
            continue
        print("---", needle, "@", i)
        print(docs_up[max(0,i-100):i+400])
        idx = i + 1
        if needle.lower() in ("drag", "between"):
            break

# 6122b7eb relevant pointer/vr hunks
print("\n======== 6122b7eb --stat ========")
print(subprocess.check_output(["git", "show", "--stat", "--format=%s", "6122b7eb"], cwd=repo, text=True)[:2000])

print("\n======== 6122b7eb pointer FramePanel/retarget hunks ======")
d = subprocess.check_output(["git", "show", "6122b7eb", "--", "pointer/helper/ft-pointer.cpp"], cwd=repo, text=True)
# print only FramePanel / pressKey related
for line in d.splitlines():
    if any(k in line for k in ("FramePanel", "pressKey", "pressPose", "dragDistance", "frametop.float", "@@")):
        print(line)
