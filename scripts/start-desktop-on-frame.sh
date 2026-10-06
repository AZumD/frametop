#!/bin/bash
# Start Frametop desktop on the Frame host. Prefer this over an inline SSH script —
# nested quoting from a PC/WSL shell has broken the health gate and start path before.
#
# Usage (on Frame, or via scripts/frame.sh --host):
#   scripts/start-desktop-on-frame.sh
# Env: FT_SCREENS FT_WIDTH FT_HEIGHT FT_PHYS_WIDTH FT_BACKEND (same as desktops.sh start)
set -euo pipefail
export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
export DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}

if ! systemctl --user is-active steamvr.service >/dev/null \
    || ! pgrep -x vrcompositor >/dev/null \
    || ! pgrep -x vrserver >/dev/null; then
  echo 'SteamVR is not healthy (need active steamvr.service + vrserver + vrcompositor).' >&2
  echo 'Recover SteamVR first (wear the headset / scripts/recover-vr.sh), then retry.' >&2
  exit 1
fi

if pgrep -f '[v]r-overlay-key frametop ' >/dev/null || pgrep -x ft-screens >/dev/null; then
  echo 'already running'
  exit 0
fi

repo=$(cd "$(dirname "$0")/.." && pwd)
session=$repo/session
log=/tmp/frametop-session.log

systemctl --user reset-failed frametop-desktop 2>/dev/null || true
# shellcheck disable=SC2086
systemd-run --user --collect --quiet --unit frametop-desktop \
  ${FT_SCREENS:+--setenv=FT_SCREENS=$FT_SCREENS} \
  ${FT_WIDTH:+--setenv=FT_WIDTH=$FT_WIDTH} \
  ${FT_HEIGHT:+--setenv=FT_HEIGHT=$FT_HEIGHT} \
  ${FT_PHYS_WIDTH:+--setenv=FT_PHYS_WIDTH=$FT_PHYS_WIDTH} \
  ${FT_BACKEND:+--setenv=FT_BACKEND=$FT_BACKEND} \
  bash -c "exec $session/frametop-session.sh > $log 2>&1"

sleep 12
echo "plasmashell processes: $(pgrep -c plasmashell 2>/dev/null || echo 0)"
if ! pgrep -f '[v]r-overlay-key frametop ' >/dev/null && ! pgrep -x ft-screens >/dev/null; then
  echo failed:
  tail -20 "$log"
  exit 1
fi

# Rock-solid spatial taskbar: ft-screens must accept toolbar commands, ft-taskbar must run,
# and the layout toolbar must be enabled (session apply may race; force-enable if needed).
ask_toolbar() {
  python3 - <<'PY'
import socket, sys
s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
s.bind(b"\0ft_desk_tb")
s.settimeout(3)
try:
    s.sendto(b"toolbar state", b"\0ft_screens")
    print(s.recv(8192).decode(errors="replace"))
except Exception as e:
    print("fail", e)
    sys.exit(1)
PY
}
reply=$(ask_toolbar 2>/dev/null || true)
if ! printf '%s' "$reply" | grep -q '^ok '; then
  echo "warning: toolbar commands missing in live ft-screens ($reply); desktop is up but taskbar will not show" >&2
  echo started
  exit 0
fi
if ! pgrep -f '^ft-taskbar ' >/dev/null; then
  echo "warning: ft-taskbar not running; starting it" >&2
  bash -c "exec -a ft-taskbar python3 \"$session/ft-taskbar.py\"" >> /tmp/frametop-taskbar.log 2>&1 &
  sleep 1
fi
# Enable if layout has it off / never applied.
python3 "$repo/layout/ft_layout.py" toolbar enable >/tmp/frametop-toolbar-enable.log 2>&1 || true
echo started
exit 0
