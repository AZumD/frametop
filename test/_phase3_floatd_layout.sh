#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/Antho/Projects/frametop-customized-main
python3 <<'PY'
from pathlib import Path
t = Path("float/ft_floatd.py").read_text()
for i, line in enumerate(t.splitlines(), 1):
    if any(x in line for x in ("ft_layout", "open_profile", "place_entry", "launch_entries", "concealed", "sys.path")):
        print(f"{i}:{line[:140]}")
PY
echo "==== upstream outputs ===="
git show upstream/main:layout/ft_layout.py | sed -n '/^def outputs/,/^def /p' | head -50
echo "==== upstream session float bits ===="
git show upstream/main:session/frametop-session.sh | grep -nE 'FLOAT|float|deco|ft_apps|spares|output-count' | head -60
