#!/bin/bash
# Restart plasmashell if it dies while the nested Frametop session is still up.
# Runs inside dbus-run-session (same private D-Bus as startplasma-wayland).
#
# Does NOT restart KWin, ft-screens, SteamVR, or the whole desktop.
# Respawns using plasmashell.env captured from the FIRST healthy plasmashell
# (/proc/PID/environ) — never the pre-Plasma outer WAYLAND_DISPLAY/ft-screens path.
set -eu

here=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
# shellcheck source=ft-shell-env.sh
. "$here/ft-shell-env.sh"

log=${FRAMETOP_SHELL_WATCH_LOG:-/tmp/frametop-plasmashell-watchdog.log}
runtime=${XDG_RUNTIME_DIR:?XDG_RUNTIME_DIR unset}
active=$runtime/session-active
envfile=$runtime/plasmashell.env
pidfile=$runtime/ft-shell-watch.pid
initialized_marker=$runtime/shell-initialized

# Startup: wait this long for first plasmashell before giving up (session may still be up).
STARTUP_GRACE_SEC=${FRAMETOP_SHELL_STARTUP_GRACE:-60}

# Burst limit: at most MAX_BURST restarts inside WINDOW_SEC, then cool down.
MAX_BURST=5
WINDOW_SEC=120
COOLDOWN_SEC=60
MIN_DELAY_SEC=1

mkdir -p "$(dirname "$log")"
ts() { date -Is; }
log_line() { printf '%s %s\n' "$(ts)" "$*" | tee -a "$log" >/dev/null; }

alive() { pgrep -x "$1" >/dev/null 2>&1; }

kwin_alive() {
  alive kwin_wayland || pgrep -x kwin_wayland >/dev/null 2>&1
}

nested_wayland_ready() {
  # Nested KWin advertises wayland-0 under the frametop runtime dir.
  [ -S "$runtime/wayland-0" ] || [ -S "$runtime/wayland-1" ]
}

screens_alive() {
  alive ft-screens && return 0
  [ -S "/run/user/$(id -u)/ft-screens-0" ] && return 0
  return 1
}

# After init: session is up only while marker exists AND KWin is alive.
session_running() {
  [ -f "$active" ] || return 1
  kwin_alive || return 1
  return 0
}

write_pidfile() {
  echo $$ > "$pidfile"
}

clear_pidfile() {
  rm -f "$pidfile"
}

cleanup_watch() {
  clear_pidfile
}
trap cleanup_watch EXIT

diagnose() {
  local reason=$1 kwin=no screens=no wl=no
  kwin_alive && kwin=yes
  screens_alive && screens=yes
  nested_wayland_ready && wl=yes
  log_line "plasmashell lost ($reason); kwin=$kwin nested_wayland=$wl ft-screens=$screens"
  if [ -f /tmp/frametop-session.log ]; then
    log_line "--- recent session log ---"
    grep -vE '^\s*$' /tmp/frametop-session.log 2>/dev/null | tail -n 20 | while IFS= read -r line; do
      printf '%s   %s\n' "$(ts)" "$line" >> "$log"
    done
    log_line "--- end session log ---"
  fi
}

find_nested_plasmashell() {
  local pid
  for pid in $(pgrep -x plasmashell 2>/dev/null || true); do
    if ft_shell_env_pid_is_nested "$pid"; then
      echo "$pid"
      return 0
    fi
  done
  return 1
}

snapshot_from_pid() {
  local pid=$1
  if ft_shell_env_capture "$pid" "$envfile"; then
    log_line "captured plasmashell.env from pid=$pid:"
    ft_shell_env_summary "$envfile" | while IFS= read -r line; do
      log_line "  $line"
    done
    touch "$initialized_marker"
    return 0
  fi
  log_line "refused to capture env from pid=$pid (not nested wayland-0/frametop)"
  return 1
}

# Startup phase: session-active alone; missing plasmashell is NOT session end.
wait_for_initial_shell() {
  local deadline=$((SECONDS + STARTUP_GRACE_SEC))
  local pid
  log_line "startup: waiting up to ${STARTUP_GRACE_SEC}s for nested KWin + plasmashell"
  while [ -f "$active" ]; do
    if pid=$(find_nested_plasmashell); then
      snapshot_from_pid "$pid" || true
      if [ -f "$initialized_marker" ]; then
        log_line "initialized; watching plasmashell pid=$pid"
        return 0
      fi
    fi
    if (( SECONDS >= deadline )); then
      # Keep waiting past grace while session-active remains — Plasma can be slow —
      # but log once so status is clear.
      if [ "${_grace_logged:-}" != 1 ]; then
        log_line "startup grace elapsed; still waiting while session-active (kwin=$(kwin_alive && echo yes || echo no) wayland-0=$(nested_wayland_ready && echo yes || echo no))"
        _grace_logged=1
      fi
    fi
    # If the session was torn down during startup, leave.
    if [ ! -f "$active" ]; then
      log_line "session-active removed during startup; exiting"
      exit 0
    fi
    sleep 0.5
  done
  log_line "session-active gone before plasmashell; exiting"
  exit 0
}

verify_nested_shell() {
  local pid=$1
  ft_shell_env_pid_is_nested "$pid" || return 1
  log_line "verified nested plasmashell pid=$pid:"
  ft_shell_env_summary "$pid" | while IFS= read -r line; do
    log_line "  $line"
  done
  return 0
}

restart_shell() {
  if [ ! -f "$envfile" ]; then
    log_line "cannot restart: $envfile missing"
    return 1
  fi
  log_line "restarting plasmashell with saved plasmashell.env"
  (
    # Clean child env then load the captured healthy recipe.
    # shellcheck disable=SC2030,SC2031
    ft_shell_env_load "$envfile"
    cd "${HOME:-/}" || true
    # Shell is gone → plain start. --replace also works if a stray shell exists.
    if alive plasmashell; then
      exec plasmashell --replace
    else
      exec plasmashell
    fi
  ) >> "$log" 2>&1 &
  disown || true

  local i pid
  for i in $(seq 1 60); do
    if pid=$(find_nested_plasmashell); then
      verify_nested_shell "$pid" && return 0
    fi
    session_running || return 1
    sleep 0.25
  done
  log_line "plasmashell did not come back with nested env"
  return 1
}

# --- main ---
write_pidfile
log_line "watchdog start pid=$$ runtime=$runtime"
rm -f "$initialized_marker"
# Never write a pre-Plasma "session.env" as the restart recipe.
wait_for_initial_shell

burst=0
window_start=$(date +%s)

while [ -f "$active" ]; do
  if ! session_running; then
    log_line "session ending (active or kwin gone); exiting"
    exit 0
  fi

  if pid=$(find_nested_plasmashell); then
    # Refresh snapshot occasionally from the live healthy shell.
    snapshot_from_pid "$pid" || true
    while pid=$(find_nested_plasmashell); do
      session_running || { log_line "session ending; exiting"; exit 0; }
      sleep 2
    done
    diagnose "process exited"
  else
    diagnose "not running"
  fi

  session_running || { log_line "session ending after plasmashell loss; not restarting"; exit 0; }

  now=$(date +%s)
  if (( now - window_start >= WINDOW_SEC )); then
    burst=0
    window_start=$now
  fi
  burst=$((burst + 1))
  if (( burst > MAX_BURST )); then
    log_line "restart storm: $burst attempts in ${WINDOW_SEC}s; cooling down ${COOLDOWN_SEC}s"
    sleep "$COOLDOWN_SEC"
    burst=0
    window_start=$(date +%s)
    session_running || exit 0
  fi

  delay=$(( MIN_DELAY_SEC * (1 << (burst - 1)) ))
  (( delay > 30 )) && delay=30
  log_line "backoff ${delay}s before restart (burst $burst/$MAX_BURST)"
  sleep "$delay"
  session_running || exit 0
  restart_shell || true
done

log_line "watchdog exit"
exit 0
