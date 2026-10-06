#!/usr/bin/env bash
# Revive the nested Frametop desktop after a VR/flat game or SteamVR bounce.
# Does NOT restart SteamVR, gamescope, or steam. Prefer this over ad-hoc
# _fix_desktop_* / _start_desktop_* rituals.
#
# Usage:
#   scripts/revive-desktop.sh           # health check; revive if needed
#   scripts/revive-desktop.sh --check   # report only (exit 0 = healthy)
#   scripts/revive-desktop.sh --force   # stop + clean + start even if healthy
#   desktops.sh revive                  # same (syncs from a PC first)
#
# Exit: 0 healthy/revived, 1 SteamVR unhealthy, 2 ft-screens lacks --spares,
#       3 revive ran / check failed and desktop still unhealthy.
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck disable=SC1091
. "$root/scripts/_env.sh"

check_only=0
force=0
on_host=0
for arg in "$@"; do
  case $arg in
    --check) check_only=1 ;;
    --force) force=1 ;;
    --on-host) on_host=1 ;;
    -h|--help)
      sed -n '2,14p' "$0"
      exit 0
      ;;
    *)
      echo "unknown option: $arg (try --check | --force)" >&2
      exit 2
      ;;
  esac
done

# From a PC, re-enter on the Frame so all paths (desktops.sh, start-desktop) are local.
if [ "$FRAME_LOCAL" != 1 ] && [ "$on_host" != 1 ]; then
  echo "Frametop desktop revive (via $FRAME_HOST)"
  flags=()
  [ "$check_only" = 1 ] && flags+=(--check)
  [ "$force" = 1 ] && flags+=(--force)
  exec ssh -o BatchMode=yes "$FRAME_HOST" \
    "cd $(printf %q "$FRAME_REPO") && bash scripts/revive-desktop.sh --on-host $(printf '%q ' "${flags[@]}")"
fi

echo "Frametop desktop revive"
echo "Running on this Steam Frame from $FRAME_REPO"

export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
export DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}
cd "$FRAME_REPO"
repo=$FRAME_REPO

steamvr_ok() {
  systemctl --user is-active steamvr.service >/dev/null 2>&1 \
    && pgrep -x vrcompositor >/dev/null \
    && pgrep -x vrserver >/dev/null
}

has_spares() {
  local bin=$repo/screens/build/ft-screens
  [ -x "$bin" ] && grep -aq -- '--spares' "$bin"
}

desktop_running() {
  pgrep -x ft-screens >/dev/null || pgrep -f '[v]r-overlay-key frametop ' >/dev/null
}

ask_state() {
  python3 - <<'PY'
import socket, sys
s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
s.bind(b"\0ft_revive")
s.settimeout(3)
try:
    s.sendto(b"state", b"\0ft_screens")
    print(s.recv(4096).decode(errors="replace").strip())
    sys.exit(0)
except Exception as e:
    print("fail", e)
    sys.exit(1)
PY
}

ask_toolbar() {
  python3 - <<'PY'
import socket, sys
s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
s.bind(b"\0ft_revive_tb")
s.settimeout(3)
try:
    s.sendto(b"toolbar state", b"\0ft_screens")
    print(s.recv(8192).decode(errors="replace").strip())
    sys.exit(0)
except Exception as e:
    print("fail", e)
    sys.exit(1)
PY
}

report() {
  echo "=== revive-desktop health ==="
  if steamvr_ok; then echo "steamvr=ok"; else echo "steamvr=BAD"; fi
  if has_spares; then echo "ft-screens-spares=ok"; else echo "ft-screens-spares=MISSING"; fi
  if desktop_running; then echo "desktop=running"; else echo "desktop=down"; fi
  echo "plasmashell=$(pgrep -c -x plasmashell 2>/dev/null || echo 0)"
  echo "kwin_wayland=$(pgrep -c -x kwin_wayland 2>/dev/null || echo 0)"
  if pgrep -f '^ft-taskbar ' >/dev/null; then echo "ft-taskbar=yes"; else echo "ft-taskbar=no"; fi
  if [ -S "$XDG_RUNTIME_DIR/ft-screens-0" ]; then echo "socket=yes"; else echo "socket=no"; fi
  if [ -f "$XDG_RUNTIME_DIR/frametop/plasmashell.env" ]; then echo "plasmashell.env=yes"; else echo "plasmashell.env=no"; fi
  st=$(ask_state 2>/dev/null || true)
  echo "state=${st:-fail}"
  tb=$(ask_toolbar 2>/dev/null || true)
  echo "toolbar=${tb:-fail}"
}

healthy() {
  steamvr_ok || return 1
  has_spares || return 1
  desktop_running || return 1
  pgrep -x plasmashell >/dev/null || return 1
  [ -S "$XDG_RUNTIME_DIR/ft-screens-0" ] || return 1
  [ -f "$XDG_RUNTIME_DIR/frametop/plasmashell.env" ] || return 1
  ask_state >/dev/null 2>&1 || return 1
  return 0
}

ensure_toolbar() {
  if printf '%s' "$(ask_toolbar 2>/dev/null || true)" | grep -q '^ok '; then
    if ! pgrep -f '^ft-taskbar ' >/dev/null; then
      echo "starting missing ft-taskbar"
      bash -c "exec -a ft-taskbar python3 \"$repo/session/ft-taskbar.py\"" >> /tmp/frametop-taskbar.log 2>&1 &
      sleep 1
    fi
    python3 "$repo/layout/ft_layout.py" toolbar enable >/tmp/frametop-toolbar-enable.log 2>&1 || true
  fi
}

if ! steamvr_ok; then
  report
  echo >&2
  echo "SteamVR is not healthy (need steamvr.service + vrserver + vrcompositor)." >&2
  echo "Recover SteamVR first: $repo/scripts/recover-vr.sh --yes  (then wear the headset / start SteamVR)." >&2
  echo "Do not use revive-desktop to fix SteamVR itself." >&2
  exit 1
fi

if ! has_spares; then
  report
  echo >&2
  echo "ft-screens binary is missing --spares (float slots). Rebuild, then revive again:" >&2
  echo "  bash scripts/rebuild-screens-on-frame.sh" >&2
  echo "  bash scripts/revive-desktop.sh --force" >&2
  echo "Or from a PC: bash test/_fix_desktop_spares_mismatch.sh" >&2
  exit 2
fi

report
if [ "$force" != 1 ] && healthy; then
  echo "desktop healthy — nothing to revive"
  ensure_toolbar
  exit 0
fi

if [ "$check_only" = 1 ]; then
  echo "desktop unhealthy (check-only; not reviving)"
  exit 3
fi

echo "=== revive: stop leftovers + clear stale sockets ==="
# Prefer the Frame-local stop path (same SIGTERM-before-unit order as desktops.sh).
bash "$repo/desktops.sh" stop 2>&1 || true
rm -f "$XDG_RUNTIME_DIR"/ft-screens-0 "$XDG_RUNTIME_DIR"/ft-screens-0.lock 2>/dev/null || true
if [ -d "$XDG_RUNTIME_DIR/frametop" ] && ! pgrep -x kwin_wayland >/dev/null; then
  echo "clearing stale $XDG_RUNTIME_DIR/frametop"
  rm -rf "$XDG_RUNTIME_DIR/frametop" 2>/dev/null || true
fi
sleep 2

echo "=== revive: start desktop ==="
bash "$repo/scripts/start-desktop-on-frame.sh"
sleep 5
report
ensure_toolbar

if healthy; then
  echo "revive ok"
  exit 0
fi
echo "revive failed — see /tmp/frametop-session.log and /tmp/frametop-screens.log" >&2
tail -20 /tmp/frametop-session.log 2>/dev/null || true
exit 3
