#!/bin/bash
# Shared helpers: capture / load a plasmashell environment safely (no eval).
# Sourced by ft-shell-watch.sh and ft-shell-restart.sh.
#
# File format: NUL-separated KEY=VALUE records (same as /proc/*/environ),
# filtered to keys plasmashell needs. Loading uses printf -v (no shell expansion).

# Keys / prefixes safe to copy from a healthy plasmashell into respawns.
ft_shell_env_keep() {
  case $1 in
    HOME|USER|LOGNAME|PATH|LANG|LANGUAGE|SHELL|DISPLAY|SESSION_MANAGER|DESKTOP_SESSION|TERM|TZ)
      return 0 ;;
    XDG_*|DBUS_*|WAYLAND_*|QT_*|KDE_*|KWIN_*|PLASMA_*|LC_*|KS*|GSM_*|GDK_*|GTK_*|PAM_*|XAUTH*)
      return 0 ;;
    *) return 1 ;;
  esac
}

# Write NUL-separated env from /proc/$pid/environ → $dest (atomic replace).
# Returns 1 if the process does not look like nested Frametop plasmashell.
ft_shell_env_capture() {
  local pid=$1 dest=$2
  local proc_env=$dest.tmp.$$
  local runtime_ok=0 wayland_ok=0
  [ -r "/proc/$pid/environ" ] || return 1
  : > "$proc_env"
  while IFS= read -r -d '' entry; do
    case $entry in
      *=*) ;;
      *) continue ;;
    esac
    local k=${entry%%=*}
    local v=${entry#*=}
    [[ $k =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    ft_shell_env_keep "$k" || continue
    case $k in
      XDG_RUNTIME_DIR)
        case $v in */frametop) runtime_ok=1 ;; esac ;;
      WAYLAND_DISPLAY)
        # Nested KWin socket name (not the outer ft-screens absolute path).
        case $v in wayland-0|wayland-[0-9]*) wayland_ok=1 ;; esac ;;
    esac
    printf '%s=%s\0' "$k" "$v" >> "$proc_env"
  done < "/proc/$pid/environ"
  if [ "$runtime_ok" != 1 ] || [ "$wayland_ok" != 1 ]; then
    rm -f "$proc_env"
    return 1
  fi
  mv -f "$proc_env" "$dest"
  return 0
}

# Load NUL-separated env file into the current shell (exports). No eval.
ft_shell_env_load() {
  local file=$1
  local entry k v
  [ -f "$file" ] || return 1
  while IFS= read -r -d '' entry; do
    case $entry in
      *=*) ;;
      *) continue ;;
    esac
    k=${entry%%=*}
    v=${entry#*=}
    [[ $k =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    ft_shell_env_keep "$k" || continue
    # Literal assign — values from the file are not re-parsed as shell.
    printf -v "$k" '%s' "$v"
    export "$k"
  done < "$file"
  return 0
}

# Human-readable dump of a few critical keys from a NUL env file or live pid.
ft_shell_env_summary() {
  local src=$1
  if [ -f "$src" ]; then
    tr '\0' '\n' < "$src" | awk -F= '
      $1=="XDG_RUNTIME_DIR"||$1=="WAYLAND_DISPLAY"||$1=="DISPLAY"||$1=="XDG_SESSION_TYPE"||$1=="DBUS_SESSION_BUS_ADDRESS"||$1=="PATH" {
        print $1"="substr($0,index($0,"=")+1)
      }'
  elif [ -r "/proc/$src/environ" ]; then
    tr '\0' '\n' < "/proc/$src/environ" | awk -F= '
      $1=="XDG_RUNTIME_DIR"||$1=="WAYLAND_DISPLAY"||$1=="DISPLAY"||$1=="XDG_SESSION_TYPE"||$1=="DBUS_SESSION_BUS_ADDRESS"||$1=="PATH" {
        print $1"="substr($0,index($0,"=")+1)
      }'
  fi
}

# True if pid's environ looks like nested Frametop plasmashell (wayland-0 + …/frametop).
ft_shell_env_pid_is_nested() {
  local pid=$1 line runtime=no wayland=no
  [ -r "/proc/$pid/environ" ] || return 1
  while IFS= read -r line; do
    case $line in
      XDG_RUNTIME_DIR=*/frametop) runtime=yes ;;
      WAYLAND_DISPLAY=wayland-[0-9]*) wayland=yes ;;
    esac
  done < <(tr '\0' '\n' < "/proc/$pid/environ")
  [ "$runtime" = yes ] && [ "$wayland" = yes ]
}
