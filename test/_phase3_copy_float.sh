#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/Antho/Projects/frametop-customized-main

python3 <<'PY'
from pathlib import Path
import re
t = Path("/tmp/ft-phase3-up/float/ft_floatd.py").read_text()
for k in ["profile", "open_profile", "frametop-layout", "place_entry", "launch_entries",
          "concealed", "FLOAT_SLOTS", "frametop.float", "dock_all", "float pointer", "ft_layout"]:
    print(f"{k}: {t.count(k)}")
print("defs:")
for m in re.finditer(r"^def (\w+)", t, re.M):
    name = m.group(1)
    if any(x in name for x in ("profile", "place", "launch", "capture", "concealed", "dock", "float", "spare")):
        print(" ", name)
PY

# Copy additive trees (overwrite if re-running)
rm -rf float decoration
cp -a /tmp/ft-phase3-up/float /tmp/ft-phase3-up/decoration .
mkdir -p docs
cp /tmp/ft-phase3-up/docs/floating-windows.md docs/floating-windows.md
# Strip upstream profile.md marketing from floating-windows that assumes upstream profiles —
# keep the file; we'll edit later to point at our Spatial Profiles.

ls -la float decoration docs/floating-windows.md
echo "==== our outputs() ===="
sed -n '2919,2965p' layout/ft_layout.py
