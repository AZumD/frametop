#!/usr/bin/env bash
# Reproduce systemd-run desktop start with full tracing of ft-screens argv.
set -u
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
set -euo pipefail
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export DBUS_SESSION_BUS_ADDRESS=unix:path=$XDG_RUNTIME_DIR/bus
repo=/home/steamos/dev/frametop
cd "$repo"

echo "=== kill stuck ft-layout / leftovers ==="
pkill -f '[f]t-layout' 2>/dev/null || true
pkill -x ft-screens 2>/dev/null || true
bash desktops.sh stop 2>&1 || true
rm -f "$XDG_RUNTIME_DIR"/ft-screens-0 "$XDG_RUNTIME_DIR"/ft-screens-0.lock
rm -rf "$XDG_RUNTIME_DIR/frametop" 2>/dev/null || true
sleep 1

echo "=== container-up ==="
bash scripts/container-up.sh 2>&1 | tail -10

echo "=== direct distrobox ft-screens (10s) ==="
socket=ft-screens-0
read -ra screen_args <<< "$(layout/ft-layout screen-args)"
float_slots=8
echo "argv: --socket $socket ${screen_args[*]} --spares $float_slots"
: > /tmp/frametop-screens.log
"$HOME/.local/bin/distrobox" enter dev -- \
  "$repo/screens/build/ft-screens" --socket "$socket" \
  "${screen_args[@]}" --spares "$float_slots" \
  > /tmp/frametop-screens.log 2>&1 < /dev/null &
spid=$!
for i in $(seq 1 40); do
  if [ -S "$XDG_RUNTIME_DIR/$socket" ]; then echo "socket up at ${i}*0.25s"; break; fi
  sleep 0.25
done
if [ -S "$XDG_RUNTIME_DIR/$socket" ]; then
  echo DIRECT_OK
  pgrep -ax ft-screens | head -3
else
  echo DIRECT_FAIL
  wait $spid || true
  echo "---- screens log ----"
  cat /tmp/frametop-screens.log
fi

# If direct worked, start full session (stop test screens first)
if [ -S "$XDG_RUNTIME_DIR/$socket" ]; then
  pkill -x ft-screens 2>/dev/null || true
  sleep 1
  rm -f "$XDG_RUNTIME_DIR"/ft-screens-0 "$XDG_RUNTIME_DIR"/ft-screens-0.lock
  echo "=== start-desktop-on-frame ==="
  bash scripts/start-desktop-on-frame.sh
  sleep 6
  pgrep -ax ft-screens | head -3 || echo missing_screens
  pgrep -c plasmashell || echo 0
  test -f "$XDG_RUNTIME_DIR/frametop/plasmashell.env" && echo env=yes || echo env=no
  python3 - <<'PY'
import socket
s=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM)
s.bind(b"\0ft_desk_ok")
s.settimeout(3)
try:
  s.sendto(b"state", b"\0ft_screens")
  print("state", s.recv(4096).decode(errors="replace"))
except Exception as e:
  print("state fail", e)
PY
fi
EOF
