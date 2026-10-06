#!/usr/bin/env bash
# Probe Frame hands install + PC→Frame ft-handsctl forward. Safe: status/cutouts state only.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
. "$root/scripts/_env.sh"

echo "== sync =="
"$root/scripts/sync.sh"

echo "== Frame install bits =="
ssh -o BatchMode=yes "$FRAME_HOST" '
  set +e
  echo "repo_ctl=$(test -x ~/dev/frametop/hands/ft-handsctl && echo yes || echo no)"
  echo "link=$(test -L ~/.local/bin/ft-handsctl && echo yes || echo no)"
  echo "camd_caps=$(getcap ~/dev/frametop/hands/build/ft-camd 2>/dev/null || true)"
  echo "camd_unit=$(systemctl --user is-enabled frametop-camd.service 2>&1 || true)"
  echo "hands_unit=$(systemctl --user is-enabled frametop-hands.service 2>&1 || true)"
  echo "steamvr=$(systemctl --user is-active steamvr.service 2>&1 || true)"
'

echo "== PC ./hands/ft-handsctl status (forward) =="
"$root/hands/ft-handsctl" status || true

echo "== done =="
