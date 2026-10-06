#!/usr/bin/env bash
set -u
ROOT=/mnt/c/Users/Antho/Projects/frametop-stage1-chrome
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
cd /home/steamos/dev/frametop/screens
echo "=== nm Toolbar ==="
nm build/vr.o 2>/dev/null | grep Toolbar | head -15
echo "=== strings frametop.toolbar ==="
strings build/ft-screens | grep frametop.toolbar | head -10
echo "=== running ft-screens mtime vs build ==="
pgrep -x ft-screens -a
stat -c '%y %n' build/ft-screens
EOF
