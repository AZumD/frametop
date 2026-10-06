#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/Antho/Projects/frametop-customized-main
git diff HEAD --stat -- screens/compositor.c screens/vr.cpp screens/vr.h
python3 <<'PY'
from pathlib import Path
c=Path("screens/compositor.c").read_text()
v=Path("screens/vr.cpp").read_text()
h=Path("screens/vr.h").read_text()
checks=[
 ("compositor fractional_scale include", "wlr_fractional_scale_v1.h" in c),
 ("compositor MAX 24", "#define MAX_SCREENS 24" in c),
 ("compositor --spares", "--spares" in c),
 ("compositor ft_vr_float", "ft_vr_float" in c),
 ("vr alone", "bool alone" in v),
 ("vr chrome !alone keep-alive", "!s.alone && s.controls" in v),
 ("vr keyboard.h", '#include "keyboard.h"' in v),
 ("vr keyboard::EndDragBy", "keyboard::EndDragBy" in v),
 ("vr floatOn", "floatOn" in v),
 ("vr frametop.float", "frametop.float" in v),
 ("vr CropOverlay", "CropOverlay" in v),
 ("vr.h ft_vr_float", "ft_vr_float" in h),
 ("vr UpdateInstrumentVisibility", "UpdateInstrumentVisibility" in v),
]
for k,ok in checks:
    print(("OK  " if ok else "MISS")+k)
print("--- key lines ---")
for path, pats in [
 ("screens/compositor.c", ["MAX_SCREENS", "spares", "ft_vr_float", "fractional_scale"]),
 ("screens/vr.h", ["ft_vr_float", "float"]),
]:
    t=Path(path).read_text().splitlines()
    print(path)
    for i,l in enumerate(t,1):
        if any(p in l for p in pats):
            if i<80 or "ft_vr" in l or "MAX_SCREENS" in l or "spares" in l.lower() or "float" in l.lower():
                if any(p in l for p in ("MAX_SCREENS","spares","ft_vr_float","floatOn","Crop","fractional")):
                    print(f"  {i}:{l[:120]}")
PY
