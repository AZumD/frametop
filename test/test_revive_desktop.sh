#!/usr/bin/env bash
# Dependency-light guards for scripts/revive-desktop.sh (no Frame / SteamVR).
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
fail=0
ok() { echo "ok: $*"; }
bad() { echo "FAIL: $*" >&2; fail=1; }

need() {
  local file=$1 needle=$2
  if grep -qF -- "$needle" "$file"; then
    ok "has $needle in ${file#$root/}"
  else
    bad "missing $needle in ${file#$root/}"
  fi
}
forbid() {
  local file=$1 needle=$2
  if grep -qF -- "$needle" "$file"; then
    bad "must not have $needle in ${file#$root/}"
  else
    ok "lacks $needle in ${file#$root/}"
  fi
}

script=$root/scripts/revive-desktop.sh
[ -f "$script" ] || { echo "missing revive-desktop.sh" >&2; exit 1; }

if bash -n "$script"; then ok "bash -n revive-desktop.sh"; else bad "bash -n revive-desktop.sh"; fi
if bash -n "$root/test/_fix_desktop_after_steamvr.sh"; then ok "bash -n _fix_desktop_after_steamvr"; else bad "bash -n wrapper"; fi
if bash -n "$root/test/_check_desktop_spares_health.sh"; then ok "bash -n _check_desktop_spares_health"; else bad "bash -n check wrapper"; fi

need "$script" 'scripts/_env.sh'
need "$script" 'steamvr.service'
need "$script" 'vrcompositor'
need "$script" 'vrserver'
need "$script" '--spares'
need "$script" 'recover-vr.sh'
need "$script" 'bash "$repo/desktops.sh" stop'
need "$script" 'start-desktop-on-frame.sh'
need "$script" 'ft-taskbar'
need "$script" 'toolbar enable'
need "$script" '--check'
need "$script" '--force'
need "$script" 'ft-screens-0.lock'

forbid "$script" 'systemctl --user restart steamvr'
forbid "$script" 'pkill -x vrserver'
forbid "$script" 'pkill -x gamescope'
forbid "$script" 'pkill -x steam'
forbid "$script" '/mnt/c/Users/Antho'

need "$root/desktops.sh" 'revive)'
need "$root/desktops.sh" 'revive-desktop.sh'

need "$root/test/_fix_desktop_after_steamvr.sh" 'revive-desktop.sh'
need "$root/test/_fix_desktop_after_steamvr.sh" '--force'
need "$root/test/_check_desktop_spares_health.sh" 'revive-desktop.sh'
need "$root/test/_check_desktop_spares_health.sh" '--check'

need "$root/docs/README/REVIVE-DESKTOP.md" 'scripts/revive-desktop.sh'
need "$root/docs/README/OVERVIEW.md" 'revive-desktop'

if [ "$fail" -ne 0 ]; then
  echo "revive-desktop checks failed" >&2
  exit 1
fi
echo "all revive-desktop checks passed"
