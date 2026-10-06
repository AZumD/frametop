#!/usr/bin/env bash
# Full go-live: setcap via .env → desktop restart → hands on.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
. "$root/scripts/_env.sh"

echo "== sync =="
"$root/scripts/sync.sh"

echo "== stop crash-loop =="
"$root/hands/ft-handsctl" off || true

echo "== setcap via frame_sudo / .env =="
"$root/hands/run.sh" caps

echo "== verify caps =="
ssh -o BatchMode=yes "$FRAME_HOST" 'getcap /home/steamos/dev/frametop/hands/build/ft-camd'

echo "== restart Frametop desktop (loads new ft-screens with cutouts) =="
"$root/desktops.sh" restart

echo "== wait for ft-screens (new binary) =="
ok=0
for i in $(seq 1 45); do
  if ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
pid=$(pgrep -x ft-screens | head -1)
[ -n "$pid" ] || exit 1
ls -l /proc/$pid/exe 2>/dev/null | grep -q '(deleted)' && exit 1
exit 0
EOF
  then
    echo "ft-screens up (new binary) after ${i} tries"
    ok=1
    break
  fi
  sleep 2
done
[ "$ok" = 1 ] || { echo "ft-screens did not come up cleanly" >&2; "$root/desktops.sh" status || true; exit 1; }

echo "== hands on =="
"$root/hands/ft-handsctl" on

echo "== cutouts on =="
"$root/hands/ft-handsctl" cutouts on || true

echo "== final =="
"$root/hands/ft-handsctl" status
"$root/hands/ft-handsctl" cutouts state || true
ssh -o BatchMode=yes "$FRAME_HOST" 'ls -la /run/user/1000/frametop-hands/ 2>&1 || true'
echo DONE
