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
if pgrep -f '[v]r-overlay-key frametop ' >/dev/null || pgrep -x ft-screens >/dev/null; then
  echo started
  exit 0
fi
echo failed:
tail -20 "$log"
exit 1
