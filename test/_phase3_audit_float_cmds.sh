#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/Antho/Projects/frametop-customized-main
python3 <<'PY'
from pathlib import Path
import re
v=Path('screens/vr.cpp').read_text()
# float-related command handlers and symbols
need=['ft_vr_float_create','ft_vr_float_output','floatOn','CropOverlay','frametop.float',
      'sscanf(cmd, "float ','"unfloat"','"dock"','set_panel','titleCarry','carry',
      'FLOAT_MARGIN','cropW','cropH','sub']
for n in need:
    print(f"{n!r}: {v.count(n)}")
# extract float command section from ft_vr_command
idx=v.find('void ft_vr_command')
chunk=v[idx:idx+25000]
for pat in ['float ','unfloat','dock','close ','crop','scale ','resize']:
    if pat in chunk:
        print('in ft_vr_command mentions', repr(pat))
# list sscanf/strncmp float-related in command
for m in re.finditer(r'.{0,20}(float|unfloat|dock|crop|carry|title).{0,60}', chunk):
    s=m.group(0).strip()
    if 'floatOn' in s or 'Float' in s or 'unfloat' in s or 'dock' in s or 'crop' in s or 'carry' in s:
        print('CMD:', s[:100])
PY
echo "==== floatd screens.ask patterns ===="
grep -nE 'screens\.(ask|send)|ask\(|"float |"unfloat|"dock |"size |"scale |"pose ' float/ft_floatd.py | head -40
echo "==== pointer frametop.screen ===="
grep -n 'frametop\.screen\|frametop\.\|IsDesktop\|DesktopPanel' pointer/helper/ft-pointer.cpp | head -30
