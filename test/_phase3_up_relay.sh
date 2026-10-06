#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/Antho/Projects/frametop-customized-main
git show upstream/main:input/input-relay.py > /tmp/up-relay.py
python3 <<'PY'
from pathlib import Path
t = Path('/tmp/up-relay.py').read_text()
for needle in ['float_toggle', 'dock_all', 'FLOAT', 'frametop_float', 'key_bindings', 'float pointer', 'dock all']:
    print(needle, t.count(needle))
# print relevant sections
lines = t.splitlines()
for i,l in enumerate(lines):
    if any(x in l for x in ('float_toggle','dock_all','FLOAT_ACTIONS','frametop_float','key_bindings','float pointer','dock all','Meta+Shift')):
        for j in range(max(0,i-2), min(len(lines), i+8)):
            print(f'{j+1}:{lines[j]}')
        print('---')
PY
