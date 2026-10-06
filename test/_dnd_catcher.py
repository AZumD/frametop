#!/usr/bin/env python3
"""Compare UpdateCatcher overlay sets and FocusLeave; 0a88a6b7 patch content."""
from pathlib import Path
import subprocess

repo = Path("/mnt/c/Users/Antho/Projects/frametop-customized-main")

def show(ref, path):
    return subprocess.check_output(["git", "show", f"{ref}:{path}"], cwd=repo).decode("utf-8", "replace")

ours_vr = (repo / "screens/vr.cpp").read_text(encoding="utf-8", errors="replace")
up_vr = show("upstream/main", "screens/vr.cpp")
ours_ptr = (repo / "pointer/helper/ft-pointer.cpp").read_text(encoding="utf-8", errors="replace")
up_ptr = show("upstream/main", "pointer/helper/ft-pointer.cpp")

def extract_fn(text, name, limit=120):
    # find "void Name" or "void Name("
    i = text.find(f"void {name}(")
    if i < 0:
        i = text.find(f"void {name} ")
    if i < 0:
        return f"MISSING {name}"
    # brace match roughly by lines until blank+void or next top-level
    lines = text[i:].splitlines()
    out = []
    depth = 0
    started = False
    for line in lines[:limit]:
        out.append(line)
        depth += line.count("{") - line.count("}")
        if "{" in line:
            started = True
        if started and depth <= 0:
            break
    return "\n".join(out)

print("===== OURS UpdateCatcher =====")
print(extract_fn(ours_vr, "UpdateCatcher", 100))
print("\n===== UP UpdateCatcher =====")
print(extract_fn(up_vr, "UpdateCatcher", 100))

print("\n===== OURS FocusLeave contexts =====")
idx = 0
while True:
    i = ours_vr.find("FocusLeave", idx)
    if i < 0:
        break
    print(ours_vr[i-300:i+350])
    print("---")
    idx = i + 1

print("\n===== UP FocusLeave contexts =====")
idx = 0
while True:
    i = up_vr.find("FocusLeave", idx)
    if i < 0:
        break
    print(up_vr[i-300:i+350])
    print("---")
    idx = i + 1

# 0a88a6b7 full patch for pointer and vr
print("\n===== 0a88a6b7 files =====")
print(subprocess.check_output(["git", "show", "--name-only", "--format=", "0a88a6b7"], cwd=repo, text=True))

print("\n===== 0a88a6b7 pointer diff (truncated) =====")
d = subprocess.check_output(["git", "show", "0a88a6b7", "--", "pointer/helper/ft-pointer.cpp"], cwd=repo, text=True)
print(d[:8000])

print("\n===== 0a88a6b7 vr diff (truncated) =====")
d = subprocess.check_output(["git", "show", "0a88a6b7", "--", "screens/vr.cpp"], cwd=repo, text=True)
print(d[:12000])
