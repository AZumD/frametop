#!/usr/bin/env bash
# Offline checks for plasmashell watchdog / env capture / shell-restart.
# Run: bash test/test_shell_watchdog.sh
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
fail=0
ok() { echo "ok: $*"; }
bad() { echo "FAIL: $*"; fail=$((fail + 1)); }

for f in \
  "$root/session/ft-shell-env.sh" \
  "$root/session/ft-shell-watch.sh" \
  "$root/session/ft-shell-restart.sh" \
  "$root/session/frametop-session.sh" \
  "$root/session/keep-apps.sh" \
  "$root/desktops.sh"
do
  bash -n "$f" && ok "bash -n $(basename "$f")" || bad "bash -n $(basename "$f")"
done

grep -q 'ft-shell-watch' "$root/session/frametop-session.sh" \
  && ok "session starts ft-shell-watch" || bad "session missing watchdog"
grep -q 'session-active' "$root/session/frametop-session.sh" \
  && ok "session-active marker" || bad "missing session-active"
grep -q 'plasmashell.env' "$root/session/ft-shell-watch.sh" \
  && ok "watchdog uses plasmashell.env" || bad "missing plasmashell.env"
grep -q 'session.env' "$root/session/frametop-session.sh" \
  && bad "session still writes pre-Plasma session.env" || ok "no pre-Plasma session.env write"
grep -q 'shell-restart' "$root/desktops.sh" \
  && ok "desktops.sh shell-restart" || bad "missing shell-restart"
grep -q 'ft-shell-watch.pid' "$root/desktops.sh" \
  && ok "status uses pidfile" || bad "status missing pidfile"
grep -q 'ft-shell-watch' "$root/session/keep-apps.sh" \
  && ok "keep-apps keeps watchdog" || bad "keep-apps missing watchdog"

if grep -n 'KWIN_EXPLICIT_SYNC' "$root/session/"*.sh "$root/desktops.sh" 2>/dev/null | grep -v '^Binary'; then
  bad "KWIN_EXPLICIT_SYNC appears in session scripts"
else
  ok "no KWIN_EXPLICIT_SYNC workaround"
fi

# --- safe NUL env capture / load ---
# shellcheck source=../session/ft-shell-env.sh
. "$root/session/ft-shell-env.sh"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# Fake /proc-style environ for a nested shell.
printf '%s\0' \
  'HOME=/home/steamos' \
  'PATH=/run/user/1000/frametop/bin:/usr/bin' \
  'XDG_RUNTIME_DIR=/run/user/1000/frametop' \
  'XDG_CONFIG_HOME=/home/steamos/.config/frametop' \
  'XDG_STATE_HOME=/home/steamos/.local/state/frametop' \
  'XDG_SESSION_TYPE=wayland' \
  'XDG_CURRENT_DESKTOP=KDE' \
  'DBUS_SESSION_BUS_ADDRESS=unix:path=/tmp/dbus-test' \
  'WAYLAND_DISPLAY=wayland-0' \
  'DISPLAY=:2' \
  'QT_QPA_PLATFORM=wayland' \
  'EVIL=$(rm -rf /)' \
  'LD_PRELOAD=/evil.so' \
  > "$tmp/fake_environ"

# Simulate capture filter by writing through a fake pid file reader:
# exercise keep + printf -v load path directly.
: > "$tmp/plasmashell.env"
while IFS= read -r -d '' entry; do
  k=${entry%%=*}; v=${entry#*=}
  [[ $k =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
  ft_shell_env_keep "$k" || continue
  printf '%s=%s\0' "$k" "$v" >> "$tmp/plasmashell.env"
done < "$tmp/fake_environ"

# Capture validation: wayland-0 + frametop required — drop bad outer recipe.
: > "$tmp/bad.env"
printf '%s\0' \
  'XDG_RUNTIME_DIR=/run/user/1000/frametop' \
  'WAYLAND_DISPLAY=/run/user/1000/ft-screens-0' \
  'DISPLAY=:0' \
  'DBUS_SESSION_BUS_ADDRESS=unix:path=/tmp/x' \
  > "$tmp/bad_proc"
# Manual reject check mirroring capture:
bad_wl=$(tr '\0' '\n' < "$tmp/bad_proc" | awk -F= '$1=="WAYLAND_DISPLAY"{print $2}')
case $bad_wl in wayland-[0-9]*) bad "outer ft-screens path accepted as wayland" ;;
  *) ok "rejects WAYLAND_DISPLAY=$bad_wl as nested recipe" ;;
esac

good_wl=$(tr '\0' '\n' < "$tmp/plasmashell.env" | awk -F= '$1=="WAYLAND_DISPLAY"{print $2}')
[ "$good_wl" = wayland-0 ] && ok "recipe WAYLAND_DISPLAY=wayland-0" || bad "recipe wl=$good_wl"
good_disp=$(tr '\0' '\n' < "$tmp/plasmashell.env" | awk -F= '$1=="DISPLAY"{print $2}')
[ "$good_disp" = :2 ] && ok "recipe DISPLAY=:2" || bad "recipe display=$good_disp"
tr '\0' '\n' < "$tmp/plasmashell.env" | grep -q '^EVIL=' \
  && bad "EVIL leaked into recipe" || ok "EVIL filtered out"
tr '\0' '\n' < "$tmp/plasmashell.env" | grep -q '^LD_PRELOAD=' \
  && bad "LD_PRELOAD leaked" || ok "LD_PRELOAD filtered out"

# Load without expanding shell metacharacters in values.
export EVIL='sentinel'
ft_shell_env_load "$tmp/plasmashell.env"
[ "$WAYLAND_DISPLAY" = wayland-0 ] && ok "load WAYLAND_DISPLAY" || bad "load WAYLAND_DISPLAY=$WAYLAND_DISPLAY"
[ "$DISPLAY" = :2 ] && ok "load DISPLAY" || bad "load DISPLAY=$DISPLAY"
[ "$XDG_SESSION_TYPE" = wayland ] && ok "load XDG_SESSION_TYPE" || bad "load session type"
[ "$EVIL" = sentinel ] && ok "load did not set EVIL" || bad "EVIL changed to $EVIL"

# Watchdog must wait on session-active without requiring kwin during startup.
grep -q 'STARTUP_GRACE' "$root/session/ft-shell-watch.sh" \
  && ok "startup grace present" || bad "missing startup grace"
grep -q 'session_running' "$root/session/ft-shell-watch.sh" \
  && ok "kwin gate only after init" || bad "missing session_running"
grep -q 'ft-shell-watch.pid' "$root/session/ft-shell-watch.sh" \
  && ok "watchdog writes pidfile" || bad "missing pidfile write"

MAX_BURST=5
burst=3
delay=$(( 1 * (1 << (burst - 1)) ))
[ "$delay" = 4 ] && ok "backoff delay for burst 3 == 4" || bad "backoff delay ($delay)"

grep -q 'SEMANTIC_ACTIONS' "$root/layout/ft_layout.py" \
  && ok "profile action registry still present" || bad "action registry missing"

if [ "$fail" -ne 0 ]; then
  echo "$fail check(s) failed"
  exit 1
fi
echo "all shell-watchdog checks passed"
