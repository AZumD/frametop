#!/usr/bin/env python3
"""Extract upstream FramePanel / releaseLeft / hit-test snippets for surgical port."""
from pathlib import Path

up = Path("/tmp/upstream-frametop/pointer/helper/ft-pointer.cpp")
ours = Path("/mnt/c/Users/Antho/Projects/frametop-customized-main/pointer/helper/ft-pointer.cpp")

for label, p in [("UP", up), ("OURS", ours)]:
    if not p.exists():
        print(f"==== {label} MISSING {p}")
        continue
    t = p.read_text(encoding="utf-8", errors="replace")
    print(f"==== {label} len={len(t)}")
    print("FramePanel:", "FramePanel" in t)
    print("frametop.float count:", t.count("frametop.float"))
    print('SendTo ft_screens up:', t.count('SendTo(out, "ft_screens", "up")'))
    print()

    # FramePanel function
    i = t.find("bool FramePanel")
    if i < 0:
        i = t.find("// window (frametop.float")
    if i >= 0:
        print("--- FramePanel region ---")
        print(t[i : i + 900])
        print()

    # releaseLeft
    i = t.find("auto releaseLeft")
    if i >= 0:
        print("--- releaseLeft ---")
        print(t[i : i + 900])
        print()

    # press with FramePanel
    i = t.find("if (FramePanel(lastHit))")
    if i >= 0:
        print("--- FramePanel(lastHit) press ---")
        print(t[max(0, i - 200) : i + 1200])
        print()

    # hit loop FramePanel
    i = t.find("!FramePanel(key)")
    if i >= 0:
        print("--- hit FramePanel filter ---")
        print(t[max(0, i - 300) : i + 800])
        print()
