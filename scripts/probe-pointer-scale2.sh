#!/usr/bin/env bash
# Dig into screen-3 scale: what KWin thinks vs wlroots surface/buffer.
set -uo pipefail

echo "=== layout ==="
python3 - <<'PY'
import json
print(json.dumps(json.load(open("/home/steamos/.config/frametop-layout.json")), indent=2)[:2500])
PY

echo
echo "=== kscreen-doctor json (nested env) ==="
# frametop nested runtime
for rt in /run/user/1000/frametop /run/user/$(id -u)/frametop; do
  if [ -d "$rt" ]; then
    echo "runtime $rt"
    export XDG_RUNTIME_DIR=$rt
    export WAYLAND_DISPLAY=wayland-0
    kscreen-doctor -j 2>/tmp/kscreen.err | head -c 8000
    echo
    echo "stderr:"; cat /tmp/kscreen.err | tail -20
    break
  fi
done

echo
echo "=== all buffer/surface lines ever ==="
grep -E 'screen [0-9]+: (buffer|surface)' /tmp/frametop-screens.log 2>/dev/null | tail -60

echo
echo "=== wl info / scale protocols? ==="
# Does ft-screens offer fractional-scale?
grep -E 'fractional|viewport|scale' /tmp/frametop-screens.log 2>/dev/null | head -20
ls /home/steamos/frametop/screens/compositor.c
grep -n 'fractional\|viewporter\|output_scale\|buffer_scale\|wlr_output' \
  /home/steamos/frametop/screens/compositor.c | head -40
