#!/usr/bin/env bash
# After syncing session with --spares onto a Frame whose ft-screens was built
# without it, verify the rebuilt binary, smoke --spares, and start the desktop.
set -euo pipefail
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"

ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
set -euo pipefail
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export DBUS_SESSION_BUS_ADDRESS=unix:path=$XDG_RUNTIME_DIR/bus
repo=/home/steamos/dev/frametop

echo "=== binary --spares check ==="
if ! strings "$repo/screens/build/ft-screens" | grep -qF -- '--spares'; then
  echo "binary missing --spares; run scripts/rebuild-screens-on-frame.sh first"
  exit 1
fi
echo ok

echo "=== clean ==="
bash "$repo/desktops.sh" stop 2>&1 || true
pkill -x ft-screens 2>/dev/null || true
sleep 1
rm -f "$XDG_RUNTIME_DIR"/ft-screens-0 "$XDG_RUNTIME_DIR"/ft-screens-0.lock
rm -rf "$XDG_RUNTIME_DIR/frametop" 2>/dev/null || true

echo "=== smoke --spares ==="
: > /tmp/frametop-screens.log
"$HOME/.local/bin/distrobox" enter dev -- \
  "$repo/screens/build/ft-screens" --socket ft-screens-0 \
  --screen 1920x1080@1.940 --screen 2616x1080@0.947 --spares 8 \
  > /tmp/frametop-screens.log 2>&1 < /dev/null &
for i in $(seq 1 40); do
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

echo "=== start desktop ==="
bash "$repo/scripts/start-desktop-on-frame.sh"
sleep 4
pgrep -ax ft-screens | head -2 || echo MISSING_ft-screens
echo "plasmashell=$(pgrep -c plasmashell 2>/dev/null || echo 0)"
echo "kwin=$(pgrep -c kwin_wayland 2>/dev/null || echo 0)"
test -f "$XDG_RUNTIME_DIR/frametop/plasmashell.env" && echo plasmashell.env=yes || echo plasmashell.env=no
test -S "$XDG_RUNTIME_DIR/ft-screens-0" && echo socket=yes || echo socket=no
echo "=== screens.log ==="
tail -20 /tmp/frametop-screens.log || true
python3 - <<'PY'
import socket
s=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM)
s.bind(b"\0ft_desk_go")
s.settimeout(3)
try:
  s.sendto(b"state", b"\0ft_screens")
  print("state ->", s.recv(4096).decode(errors="replace"))
except Exception as e:
  print("state fail", e)
PY
EOF
