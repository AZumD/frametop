#!/usr/bin/env bash
# Copy upstream hands/ + handcut sources into the fork (Phase 3C).
set -euo pipefail
cd /mnt/c/Users/Antho/Projects/frametop-customized-main

# Full hands tree from current upstream/main
git checkout upstream/main -- hands/

# Hand cutout sources into screens/
git show upstream/main:screens/handcut.cpp > screens/handcut.cpp
git show upstream/main:screens/handcut.h > screens/handcut.h
git show upstream/main:screens/handtest.cpp > screens/handtest.cpp

# Sanity
test -f hands/README.md
test -f hands/include/fh_hands.h
test -f hands/ft-handsctl
test -f screens/handcut.cpp
wc -l hands/README.md screens/handcut.cpp screens/handcut.h
ls hands/models/ncnn | head
echo "copied ok"
