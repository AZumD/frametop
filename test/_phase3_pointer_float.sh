#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/Antho/Projects/frametop-customized-main
git show upstream/main:pointer/helper/ft-pointer.cpp > /tmp/up-pointer.cpp
python3 <<'PY'
from pathlib import Path
up=Path('/tmp/up-pointer.cpp').read_text()
ours=Path('pointer/helper/ft-pointer.cpp').read_text()
for needle in ['IsDesktopPanel','frametop.float','frametop.screen','DesktopPanel','SendTo(out, "ft_screens", "up")','"up"']:
    print(f'{needle!r}: up={up.count(needle)} ours={ours.count(needle)}')
# show IsDesktopPanel and nearby from upstream
i=up.find('IsDesktopPanel')
if i<0:
    i=up.find('frametop.float')
print('--- upstream context ---')
print(up[max(0,i-200):i+600] if i>=0 else 'not found')
# ours context around frametop. panel check
j=ours.find('frametop.screen')
if j<0: j=ours.find('rfind("frametop."')
print('--- ours context ---')
print(ours[max(0,j-200):j+500])
PY
