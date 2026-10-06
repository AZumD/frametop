#!/usr/bin/env bash
# Apply a 3-screen profile on the Frame (restarts desktop if count differs).
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
. "$root/scripts/_env.sh"

"$root/scripts/sync.sh"

echo "== unit tests =="
python3 "$root/test/test_spatial_profiles.py"

echo "== apply Powerstation (expect restart if live has 2 screens) =="
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
set -e
~/dev/frametop/layout/ft-layout profile apply Powerstation --duration 0
echo apply_exit:$?
EOF

echo "== wait for desktop + 3 screens =="
ok=0
for i in $(seq 1 60); do
  if ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
pid=$(pgrep -x ft-screens | head -1)
[ -n "$pid" ] || exit 1
count=$(tr '\0' '\n' < /proc/$pid/environ | sed -n 's/^FT_SCREEN_COUNT=//p')
[ "$count" = 3 ] || exit 1
~/dev/frametop/layout/ft-layout profile current | grep -qx Powerstation
EOF
  then
    echo "ok after ${i} polls"
    ok=1
    break
  fi
  sleep 2
done
[ "$ok" = 1 ] || { echo "desktop did not come back on Powerstation/3 screens" >&2; exit 1; }

echo "== status =="
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
~/dev/frametop/layout/ft-layout profile current
~/dev/frametop/layout/ft-layout profile list
python3 - <<'PY'
import json, os
layout = json.load(open(os.path.expanduser("~/.config/frametop-layout.json")))
print("layout_screens", len(layout.get("screens") or []))
print("conf", open(os.path.expanduser("~/.config/frametop.conf")).read() if os.path.exists(os.path.expanduser("~/.config/frametop.conf")) else "missing")
PY
pgrep -af 'ft-screens --socket' | head -1
EOF
echo DONE
