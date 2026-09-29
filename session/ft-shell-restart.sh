#!/bin/bash
# Restart ONLY plasmashell in the running Frametop nested session.
# Uses plasmashell.env captured from a healthy nested shell (never pre-Plasma session.env).
set -euo pipefail

here=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
# shellcheck source=ft-shell-env.sh
. "$here/ft-shell-env.sh"

uid=$(id -u)
runtime=${FRAMETOP_RUNTIME:-/run/user/$uid/frametop}
envfile=$runtime/plasmashell.env
log=${FRAMETOP_SHELL_WATCH_LOG:-/tmp/frametop-plasmashell-watchdog.log}

ts() { date -Is; }
say() { printf '%s %s\n' "$(ts)" "$*" | tee -a "$log"; }

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

capture_live_if_possible() {
  local pid
  pid=$(find_nested_plasmashell) || return 1
  ft_shell_env_capture "$pid" "$envfile"
}

if [ ! -d "$runtime" ]; then
  echo "Frametop runtime $runtime not found (desktop not running?)" >&2
  exit 1
fi

if ! pgrep -x kwin_wayland >/dev/null 2>&1; then
  echo "kwin_wayland not running; refusing shell-restart" >&2
  exit 1
fi

# Prefer existing snapshot; refresh from live shell when available.
if pid=$(find_nested_plasmashell 2>/dev/null); then
  if capture_live_if_possible; then
    say "shell-restart: refreshed plasmashell.env from live pid=$pid"
  fi
fi

if [ ! -f "$envfile" ]; then
  echo "no $envfile yet (wait until plasmashell has started once)" >&2
  exit 1
fi

say "shell-restart: using $envfile"
ft_shell_env_summary "$envfile" | while IFS= read -r line; do
  say "  recipe $line"
done

# Sanity: recipe must be nested wayland-0, not outer ft-screens path.
recipe_wl=$(tr '\0' '\n' < "$envfile" | awk -F= '$1=="WAYLAND_DISPLAY"{print $2; exit}')
recipe_rt=$(tr '\0' '\n' < "$envfile" | awk -F= '$1=="XDG_RUNTIME_DIR"{print $2; exit}')
case $recipe_wl in
  wayland-[0-9]*) ;;
  *)
    echo "refusing: plasmashell.env WAYLAND_DISPLAY='$recipe_wl' (want wayland-N)" >&2
    exit 1 ;;
esac
case $recipe_rt in
  */frametop) ;;
  *)
    echo "refusing: plasmashell.env XDG_RUNTIME_DIR='$recipe_rt' (want …/frametop)" >&2
    exit 1 ;;
esac

was_alive=0
find_nested_plasmashell >/dev/null 2>&1 && was_alive=1

(
  ft_shell_env_load "$envfile"
  cd "${HOME:-/}" || true
  if [ "$was_alive" = 1 ]; then
    say "shell-restart: plasmashell --replace"
    exec plasmashell --replace
  else
    say "shell-restart: plasmashell (cold start)"
    exec plasmashell
  fi
) >> "$log" 2>&1 &
disown || true

for _ in $(seq 1 60); do
  if pid=$(find_nested_plasmashell); then
    say "shell-restart: nested plasmashell up pid=$pid"
    ft_shell_env_summary "$pid" | while IFS= read -r line; do
      say "  live $line"
    done
    # Require critical keys match nested session.
    live_wl=$(tr '\0' '\n' < "/proc/$pid/environ" | awk -F= '$1=="WAYLAND_DISPLAY"{print $2; exit}')
    live_rt=$(tr '\0' '\n' < "/proc/$pid/environ" | awk -F= '$1=="XDG_RUNTIME_DIR"{print $2; exit}')
    live_disp=$(tr '\0' '\n' < "/proc/$pid/environ" | awk -F= '$1=="DISPLAY"{print $2; exit}')
    case $live_wl in wayland-[0-9]*) ;; *)
      say "shell-restart: BAD WAYLAND_DISPLAY=$live_wl"
      echo "plasmashell came up with wrong WAYLAND_DISPLAY=$live_wl" >&2
      exit 1 ;;
    esac
    case $live_rt in */frametop) ;; *)
      say "shell-restart: BAD XDG_RUNTIME_DIR=$live_rt"
      echo "plasmashell came up with wrong XDG_RUNTIME_DIR=$live_rt" >&2
      exit 1 ;;
    esac
    echo "plasmashell restarted (pid=$pid WAYLAND_DISPLAY=$live_wl DISPLAY=$live_disp)"
    exit 0
  fi
  sleep 0.25
done

say "shell-restart: plasmashell did not come back nested"
echo "plasmashell did not come back (see $log)" >&2
exit 1
