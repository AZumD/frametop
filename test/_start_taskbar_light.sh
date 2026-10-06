#!/usr/bin/env bash
# Start ft-taskbar and enable spatial toolbar without full desktop restart (when ft-screens
# binary already includes toolbar). If toolbar socket commands fail, restart ft-screens only.
set -euo pipefail
ROOT=/mnt/c/Users/Antho/Projects/frametop-stage1-chrome
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
bash "$ROOT/scripts/sync.sh"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
set -euo pipefail
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export DBUS_SESSION_BUS_ADDRESS=unix:path=$XDG_RUNTIME_DIR/bus
repo=/home/steamos/dev/frametop
here="$repo/session"
cd "$repo"

ask_screens() {
  python3 - "$1" <<'PY'
import socket, sys
cmd = sys.argv[1].encode()
s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
s.bind(b"\0ft_tb_light")
s.settimeout(3)
s.sendto(cmd, b"\0ft_screens")
print(s.recv(8192).decode(errors="replace"))
PY
}

echo "=== ft-screens vs build ==="
pid=$(pgrep -x ft-screens || true)
if [ -n "$pid" ]; then
  exe=$(readlink -f /proc/$pid/exe)
  stat -c "proc_start %y pid=%p" /proc/$pid
  stat -c "build_mtime %y" screens/build/ft-screens
  echo "exe=$exe"
fi

echo "=== toolbar socket ==="
ask_screens "toolbar state" || true

if ! ask_screens "toolbar state" 2>/dev/null | grep -q '^ok '; then
  echo "=== restarting ft-screens only (toolbar commands missing in live process) ==="
  bash desktops.sh stop 2>&1 || true
  sleep 2
  bash scripts/start-desktop-on-frame.sh
  sleep 5
  ask_screens "toolbar state" || true
fi

if ! pgrep -f '^ft-taskbar ' >/dev/null; then
  echo "=== starting ft-taskbar ==="
  bash -c "exec -a ft-taskbar python3 \"$here/ft-taskbar.py\"" >> /tmp/frametop-taskbar.log 2>&1 &
  sleep 2
fi

echo "=== layout toolbar enable ==="
python3 layout/ft_layout.py toolbar enable 2>&1

echo "=== post ==="
pgrep -af '^ft-taskbar ' | head -2 || true
ask_screens "toolbar state"
ask_screens "state"
tail -8 /tmp/frametop-taskbar.log 2>/dev/null || true
EOF
