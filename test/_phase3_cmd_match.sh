#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/Antho/Projects/frametop-customized-main
python3 <<'PY'
from pathlib import Path
v=Path('screens/vr.cpp').read_text()
idx=v.find('void ft_vr_command')
chunk=v[idx:idx+35000]
# print every else-if / sscanf related to float features
for i,line in enumerate(chunk.splitlines()):
    if any(x in line for x in ('float','unfloat','dock','minimized','carry','sub ','pose','Crop','titleCarry','crop')):
        if 'g_float' in line or 'floatOn' in line or 'sscanf' in line or 'strncmp' in line or 'strcmp' in line or 'unfloat' in line or 'minimized' in line or 'carry' in line or line.strip().startswith('//') and ('float' in line or 'dock' in line or 'spare' in line):
            print(f'{i}:{line[:140]}')
print('--- defs ---')
for name in ['ft_vr_float_create','ft_vr_float_output','CropOverlay','SetCrop','ApplyFloat']:
    p=v.find(name)
    print(name, 'at', p)
    if p>=0:
        print(v[p:p+400].split('\n')[0][:120])
        print('...')
PY
# compare command strings floatd sends vs vr handles
python3 <<'PY'
from pathlib import Path
import re
v=Path('screens/vr.cpp').read_text()
floatd=Path('float/ft_floatd.py').read_text()
cmds=set(re.findall(r'ask\(f?"([^"]+)', floatd))
# also f-strings broken - extract templates
tmpls=re.findall(r'ask\(f"([^"]+)"', floatd)
print('floatd ask templates:')
for t in sorted(set(tmpls)):
    head=t.split()[0]
    present = head in v or t.split('{')[0].strip() in v
    # check command word
    word=t.split()[0]
    ok = f'"{word}' in v or f"'{word}" in v or f'{word} %' in v or f'{word} ' in v
    print(f'  {t!r} word={word} in_vr={ok}')
PY
