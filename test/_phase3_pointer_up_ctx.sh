#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/Antho/Projects/frametop-customized-main
python3 <<'PY'
from pathlib import Path
up=Path('/tmp/up-pointer.cpp').read_text()
ours=Path('pointer/helper/ft-pointer.cpp').read_text()
# find FramePanel usages with context
idx=0
while True:
    i=up.find('FramePanel', idx)
    if i<0: break
    print('====', i)
    print(up[max(0,i-120):i+200])
    print()
    idx=i+1
# find left release / up send
j=up.find('ft_screens", "up"')
print('==== up send ====', j)
print(up[max(0,j-400):j+200])
# ours left button release area
k=ours.find('btn trigger 0')
print('==== ours trigger 0 ====', k)
print(ours[max(0,k-300):k+200])
PY
