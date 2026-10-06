#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
. "$root/scripts/_env.sh"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
set +e
echo "=== try apply Desktop (expect fail) ==="
~/dev/frametop/layout/ft-layout profile apply Desktop --duration 0 2>&1
echo exit:$?
echo "=== try apply Powerstation ==="
~/dev/frametop/layout/ft-layout profile apply Powerstation --duration 0 2>&1
echo exit:$?
echo "=== frametop.conf SCREENS ==="
grep -E '^SCREENS=|^FLOAT' ~/.config/frametop.conf 2>&1
echo "=== FT_SCREEN_COUNT env of ft-screens ==="
pid=$(pgrep -x ft-screens | head -1)
tr '\0' '\n' < /proc/$pid/environ 2>/dev/null | grep -E 'FT_SCREEN|SCREENS|FLOAT' || true
EOF
