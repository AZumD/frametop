#!/usr/bin/env python3
"""Dump upstream cutout helpers and Screen fields used by handcut."""
from pathlib import Path
import re

vr = Path("/tmp/up-vr.cpp").read_text()
ours = Path("/mnt/c/Users/Antho/Projects/frametop-customized-main/screens/vr.cpp").read_text()

for name in ["CutterReady", "ImportCutout", "StopCutting", "SetScreenTexture", "bool cutting", "s.key", "s.buf", "void Present"]:
    print(f"\n===== UP {name} =====")
    if name.startswith("void ") or name.startswith("bool ") or name[0].isupper():
        # function
        for pat in [rf"{re.escape(name)}\(", rf"^{re.escape(name)}\b"]:
            m = re.search(pat, vr, re.M)
            if m:
                print(vr[m.start():m.start()+900])
                break
        else:
            i = vr.find(name)
            print(vr[i:i+500] if i>=0 else "missing")
    else:
        for i,l in enumerate(vr.splitlines()):
            if name in l and ("struct Screen" in "".join(vr.splitlines()[max(0,i-40):i]) or "cutting" in l or "key" in l or "buf" in l):
                if "cutting" in l or name in ("s.key","s.buf"):
                    pass
        # Screen fields
        m = re.search(r"struct Screen \{.*?\n\};", vr, re.S)
        if m and name in ("s.key","s.buf","bool cutting"):
            block = m.group(0)
            for l in block.splitlines():
                if any(k in l for k in ("key", "buf", "cutting", "shown", "width")):
                    print(l)

print("\n===== UP Screen cutout-related fields =====")
m = re.search(r"struct Screen \{.*?\n\};", vr, re.S)
for l in m.group(0).splitlines():
    if any(k in l for k in ("key", "buf", "cutting", "shown", "SharedTexture", "dmabuf")):
        print(l)

print("\n===== OURS Screen fields =====")
m = re.search(r"struct Screen \{.*?\n\};", ours, re.S)
for l in m.group(0).splitlines():
    if any(k in l for k in ("key", "buf", "cutting", "shown", "SharedTexture", "width", "floating")):
        print(l)

print("\n===== UP present / SetOverlayTexture =====")
for needle in ["SetScreenTexture", "s.key =", "s.buf", "StopCutting", "ImportCutout", "CutterReady"]:
    idxs=[m.start() for m in re.finditer(re.escape(needle), vr)]
    print(needle, len(idxs))
    for j in idxs[:3]:
        print(" ", vr[j:j+120].replace("\n"," "))

print("\n===== cutouts command in UP =====")
i = vr.find('cutouts')
# find control command
for m in re.finditer(r'cutouts[^\n]{0,80}', vr):
    if "sscanf" in vr[max(0,m.start()-40):m.start()+80] or "strncmp" in vr[max(0,m.start()-80):m.start()+20]:
        print(vr[max(0,m.start()-100):m.start()+300])
        print("---")
