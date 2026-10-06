#!/usr/bin/env python3
"""Classify dirty files into float commits vs leave-uncommitted WIP."""
from pathlib import Path
import subprocess

repo = Path("/mnt/c/Users/Antho/Projects/frametop-customized-main")
out = subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True)
print(out)

# For layout: show whether diff is only floats-related
diff = subprocess.check_output(["git", "diff", "--", "layout/ft_layout.py"], cwd=repo, text=True)
print("layout diff lines", len(diff.splitlines()))
# hunks
hunks = []
cur = []
for line in diff.splitlines():
    if line.startswith("@@"):
        if cur:
            hunks.append(cur)
        cur = [line]
    elif cur:
        cur.append(line)
if cur:
    hunks.append(cur)
for i, h in enumerate(hunks):
    text = "\n".join(h)
    floaty = any(k in text.lower() for k in ("spare", "float", "wl-", "screen_count", "outputs"))
    print(f"\n==== hunk {i} floaty={floaty} ====")
    print("\n".join(h[:40]))
