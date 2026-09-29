#!/usr/bin/env bash
# Live pointer/scale diagnosis after fractional-scale fix.
set -uo pipefail

echo "=== ft-screens binary / process ==="
ls -la /home/steamos/frametop/screens/build/ft-screens
pgrep -a ft-screens || true
ps -o lstart= -p "$(pgrep -x ft-screens | head -1)" 2>/dev/null || true
strings /home/steamos/frametop/screens/build/ft-screens | grep -E 'fractional|preferred scale|surface %dx%d|buffer %dx%d' | head

echo
echo "=== layout scales ==="
python3 - <<'PY'
import json
d=json.load(open("/home/steamos/.config/frametop-layout.json"))
for i,s in enumerate(d.get("screens",[])):
  print(f"screen{i+1}: size={s.get('size')} scale={s.get('scale',1)}")
PY

echo
echo "=== buffer/surface log lines ==="
grep -E 'screen [0-9]+: (buffer|surface)|fractional' /tmp/frametop-screens.log 2>/dev/null | tail -40

echo
echo "=== kscreen scales (nested) ==="
export XDG_RUNTIME_DIR=/run/user/1000/frametop
export WAYLAND_DISPLAY=wayland-0
kscreen-doctor -j 2>/dev/null | python3 - <<'PY'
import json,sys
d=json.load(sys.stdin)
for o in d.get("outputs",[]):
  print(f"{o.get('name')}: mode={o.get('size')} scale={o.get('scale')} pos={o.get('pos')}")
PY

echo
echo "=== compositor has fractional_scale? ==="
grep -n fractional /home/steamos/frametop/screens/compositor.c | head
