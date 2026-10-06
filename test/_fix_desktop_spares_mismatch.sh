#!/usr/bin/env bash
# Fix desktop: session passes --spares but Frame ft-screens lacked it.
# Rebuild (separate SSH), then smoke + start (separate SSH).
set -euo pipefail
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
python3 "$ROOT/test/_fix_crlf_tree.py" >/dev/null 2>&1 || true
bash "$ROOT/scripts/sync.sh"

echo "===== REBUILD ====="
ssh -o BatchMode=yes -o ServerAliveInterval=30 "$FRAME_HOST" \
  "export XDG_RUNTIME_DIR=/run/user/\$(id -u); cd /home/steamos/dev/frametop && bash desktops.sh stop; pkill -x ft-screens 2>/dev/null; rm -f \$XDG_RUNTIME_DIR/ft-screens-0 \$XDG_RUNTIME_DIR/ft-screens-0.lock; rm -rf \$XDG_RUNTIME_DIR/frametop; bash scripts/rebuild-screens-on-frame.sh; grep -aob -- '--spares' screens/build/ft-screens | head -3; echo REBUILD_DONE"

echo "===== SMOKE + START ====="
ssh -o BatchMode=yes -o ServerAliveInterval=30 "$FRAME_HOST" bash -s <<'EOF'
set -euo pipefail
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export DBUS_SESSION_BUS_ADDRESS=unix:path=$XDG_RUNTIME_DIR/bus
repo=/home/steamos/dev/frametop
cd "$repo"

if ! grep -aq -- '--spares' screens/build/ft-screens; then
  echo "binary still missing --spares"
  exit 1
fi
echo "binary has --spares"

: > /tmp/frametop-screens.log
"$HOME/.local/bin/distrobox" enter dev -- \
  "$repo/screens/build/ft-screens" --socket ft-screens-0 \
  --screen 1920x1080@1.940 --screen 2616x1080@0.947 --spares 8 \
  > /tmp/frametop-screens.log 2>&1 < /dev/null &
for i in $(seq 1 48); do
  [ -S "$XDG_RUNTIME_DIR/ft-screens-0" ] && break
  sleep 0.25
done
if [ -S "$XDG_RUNTIME_DIR/ft-screens-0" ]; then
  echo smoke_ok
  pkill -x ft-screens || true
  sleep 1
  rm -f "$XDG_RUNTIME_DIR"/ft-screens-0 "$XDG_RUNTIME_DIR"/ft-screens-0.lock
else
  echo smoke_fail
  cat /tmp/frametop-screens.log
  exit 1
fi

bash scripts/start-desktop-on-frame.sh
sleep 4
pgrep -ax ft-screens | head -2 || echo MISSING_ft-screens
echo "plasmashell=$(pgrep -c plasmashell 2>/dev/null || echo 0)"
echo "kwin=$(pgrep -c kwin_wayland 2>/dev/null || echo 0)"
test -f "$XDG_RUNTIME_DIR/frametop/plasmashell.env" && echo plasmashell.env=yes || echo plasmashell.env=no
test -S "$XDG_RUNTIME_DIR/ft-screens-0" && echo socket=yes || echo socket=no
tail -25 /tmp/frametop-screens.log || true
python3 - <<'PY'
import socket
s=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM)
s.bind(b"\0ft_desk_fix")
s.settimeout(3)
try:
  s.sendto(b"state", b"\0ft_screens")
  print("state ->", s.recv(4096).decode(errors="replace"))
except Exception as e:
  print("state fail", e)
PY
EOF
