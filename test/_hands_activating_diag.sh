#!/usr/bin/env bash
# Diagnose why frametop-camd / frametop-hands stay activating.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
. "$root/scripts/_env.sh"

ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
set +e
echo "=== units ==="
for u in frametop-camd.service frametop-hands.service steamvr.service; do
  echo "-- $u"
  systemctl --user is-active "$u" 2>&1
  systemctl --user is-failed "$u" 2>&1
  systemctl --user show "$u" -p ActiveState -p SubState -p Result -p ExecMainStatus -p NRestarts 2>&1
done

echo "=== camd journal ==="
journalctl --user -u frametop-camd.service --no-pager -n 40 -o cat 2>&1

echo "=== hands journal ==="
journalctl --user -u frametop-hands.service --no-pager -n 40 -o cat 2>&1

echo "=== caps / binaries ==="
getcap /home/steamos/dev/frametop/hands/build/ft-camd 2>&1
ls -la /home/steamos/dev/frametop/hands/build/ft-camd /home/steamos/dev/frametop/hands/build/ft-hands 2>&1

echo "=== runtime dir ==="
ls -la /run/user/1000/frametop-hands 2>&1 || echo "no frametop-hands dir"

echo "=== unit files ==="
grep -E 'ExecStart|ExecStartPre|Requisite|PartOf|After' ~/.config/systemd/user/frametop-camd.service ~/.config/systemd/user/frametop-hands.service 2>&1

echo "=== XRService / related ==="
pgrep -af XRService | head -5 || echo no-xrservice
pgrep -af 'ft-camd|ft-hands' || echo no-hands-procs

echo "=== ft-screens exe ==="
pid=$(pgrep -x ft-screens | head -1)
if [ -n "$pid" ]; then ls -l /proc/$pid/exe; else echo no-ft-screens; fi
EOF
