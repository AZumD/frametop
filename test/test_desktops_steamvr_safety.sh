#!/usr/bin/env bash
# desktops.sh must SIGTERM ft-screens before stopping the systemd unit, and must
# refuse start when SteamVR is unhealthy.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
f=$root/desktops.sh

grep -q 'SIGTERM ft-screens before stopping' "$f" \
  || grep -q 'pkill -TERM -x ft-screens' "$f" \
  || { echo "missing graceful SIGTERM of ft-screens before unit stop"; exit 1; }

# TERM must appear before 'systemctl --user stop frametop-desktop' in the stop action.
awk '
  /stop\)/ { in_stop=1 }
  in_stop && /shell-restart\)|restart\)|status\)/ { in_stop=0 }
  in_stop && /pkill -TERM -x ft-screens/ { term=NR }
  in_stop && /systemctl --user stop frametop-desktop/ { stop=NR }
  END {
    if (!term || !stop) { print "stop action missing TERM or unit stop"; exit 1 }
    if (term > stop) { print "ft-screens SIGTERM must come before systemctl stop"; exit 1 }
  }
' "$f"

grep -q 'SteamVR is not healthy' "$root/scripts/start-desktop-on-frame.sh" \
  || { echo "missing SteamVR health gate in start-desktop-on-frame.sh"; exit 1; }
grep -q 'start-desktop-on-frame.sh' "$f" \
  || { echo "desktops.sh start must call start-desktop-on-frame.sh"; exit 1; }
grep -q 'pgrep -x vrcompositor' "$root/scripts/start-desktop-on-frame.sh" \
  || { echo "missing vrcompositor health check"; exit 1; }

echo "ok: desktops.sh stop/start SteamVR safety"
