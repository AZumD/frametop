#!/usr/bin/env python3
"""Extract upstream handcut wiring points for the Phase 3C port."""
from pathlib import Path
import subprocess

repo = Path("/mnt/c/Users/Antho/Projects/frametop-customized-main")


def show(path: str) -> str:
    return subprocess.check_output(["git", "show", f"upstream/main:{path}"], text=True, cwd=repo)


vr = show("screens/vr.cpp")
Path("/tmp/up-vr.cpp").write_text(vr)
build = show("screens/build.sh")
Path("/tmp/up-screens-build.sh").write_text(build)
conf = show("session/frametop.conf.example")
Path("/tmp/up-frametop.conf.example").write_text(conf)
dev = show("setup/dev-container.sh")
Path("/tmp/up-dev-container.sh").write_text(dev)

print("=== counts in up vr.cpp ===")
for pat in ["handcut", "g_hands", "g_cutter", "UpdateCutouts", "cutouts", "Hands("]:
    print(pat, vr.count(pat))

print("\n=== build.sh hand/egl lines ===")
for i, l in enumerate(build.splitlines(), 1):
    if any(k in l.lower() for k in ("hand", "egl", "gles", "gbm", "handcut")):
        print(f"{i}:{l}")

print("\n=== conf HANDS ===")
for i, l in enumerate(conf.splitlines(), 1):
    if "HAND" in l or "hand" in l.lower():
        print(f"{i}:{l}")

print("\n=== install hands mentions ===")
inst = show("install.sh")
for i, l in enumerate(inst.splitlines(), 1):
    if "hand" in l.lower():
        print(f"{i}:{l}")

print("\n=== include + globals context ===")
for needle in ['#include "handcut.h"', "handcut::Hands", "handcut::Renderer", "void UpdateCutouts", 'cutouts ', "UpdateCutouts();"]:
    i = vr.find(needle)
    print(f"\n### {needle} @ {i}")
    if i >= 0:
        print(vr[max(0, i - 80) : i + 600])

# Find UpdateCutouts full function
i = vr.find("void UpdateCutouts(")
if i < 0:
    i = vr.find("void UpdateCutouts()")
print("\n=== UpdateCutouts body start ===")
print(vr[i : i + 2500] if i >= 0 else "MISSING")

# poll / shutdown hooks
for needle in ["UpdateCutouts()", "g_cutter", "g_hands.", "handcut::"]:
    idxs = [m.start() for m in __import__("re").finditer(__import__("re").escape(needle), vr)]
    print(f"\n{needle} occurrences: {len(idxs)}")
    for j in idxs[:8]:
        line = vr.count("\n", 0, j) + 1
        print(f"  L{line}: {vr[j:j+100].splitlines()[0]}")
