#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/Antho/Projects/frametop-customized-main
echo "compositor spares=$(grep -c spares screens/compositor.c || true) MAX=$(grep MAX_SCREENS screens/compositor.c | head -1)"
echo "vr float=$(grep -c 'frametop.float' screens/vr.cpp || true) floatOn=$(grep -c floatOn screens/vr.cpp || true)"
echo "patch sizes:" 
wc -l test/_diff_compositor_float.patch test/_diff_vr_h.patch 2>/dev/null || true
head -60 test/_diff_compositor_float.patch 2>/dev/null || true
