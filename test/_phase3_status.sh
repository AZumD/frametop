#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/Antho/Projects/frametop-customized-main
echo "branch=$(git branch --show-current) HEAD=$(git rev-parse --short HEAD)"
git status -sb | head -60
python3 <<'PY'
from pathlib import Path
for p in ["screens/compositor.c","screens/vr.cpp","screens/vr.h","pointer/helper/ft-pointer.cpp",
          "session/frametop-session.sh","input/input-relay.py","layout/ft_layout.py"]:
    t=Path(p).read_text(errors="replace")
    print(f"== {p}")
    for k in ["spares","MAX_SCREENS","frametop.float","floatOn","CropOverlay","ft_vr_float",
              "--spares","FLOAT_SLOTS","float_toggle","dock_all","frametop.float."]:
        c=t.count(k)
        if c: print(f"  {k}: {c}")
PY
ls -la float decoration 2>/dev/null | head
wc -l test/_diff_compositor_float.patch test/_float_chunks.txt test/_port_float_vr1.py 2>/dev/null || true
