#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/Antho/Projects/frametop-customized-main
git show upstream/main:screens/vr.cpp > /tmp/up-vr.cpp
git show upstream/main:screens/compositor.c > /tmp/up-compositor.c
git show upstream/main:pointer/helper/ft-pointer.cpp > /tmp/up-pointer.cpp
python3 - <<'PY'
from pathlib import Path
import re

def extract(path, start_pat, end_pat=None, n=80):
    t = Path(path).read_text(encoding='utf-8', errors='replace')
    m = re.search(start_pat, t)
    if not m:
        return f'MISSING {start_pat}'
    i = m.start()
    if end_pat:
        m2 = re.search(end_pat, t[i+1:])
        j = i + 1 + (m2.start() if m2 else 2000)
    else:
        j = i + n*80
    return t[i:j]

for label, path in [('UP','/tmp/up-vr.cpp'),('OURS','screens/vr.cpp')]:
    print(f'\n==== {label} CropOverlay ====')
    print(extract(path, r'void CropOverlay\(', r'\nvoid ', 40))
    print(f'\n==== {label} FocusLeave / press ====')
    # g_press FocusLeave block
    i = Path(path).read_text(encoding='utf-8', errors='replace').find('VREvent_FocusLeave')
    print(Path(path).read_text(encoding='utf-8', errors='replace')[i:i+500] if i>=0 else 'no FocusLeave')

print('\n==== UP compositor enter ====')
c=Path('/tmp/up-compositor.c').read_text(encoding='utf-8', errors='replace')
i=c.find('case FT_MOTION:')
print(c[i:i+900])
print('\n==== OURS compositor enter ====')
c=Path('screens/compositor.c').read_text(encoding='utf-8', errors='replace')
i=c.find('case FT_MOTION:')
print(c[i:i+900])

print('\n==== UP pressKey retarget ====')
p=Path('/tmp/up-pointer.cpp').read_text(encoding='utf-8', errors='replace')
i=p.find('if (leftHeld && !pressKey.empty())')
print(p[i:i+900] if i>=0 else 'MISSING')
print('\n==== OURS pressKey retarget ====')
p=Path('pointer/helper/ft-pointer.cpp').read_text(encoding='utf-8', errors='replace')
i=p.find('if (leftHeld && !pressKey.empty())')
print(p[i:i+900] if i>=0 else 'MISSING')
PY
