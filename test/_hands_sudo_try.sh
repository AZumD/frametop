#!/usr/bin/env bash
# Verify Frame sudo using steamos_root_pwd from the repo .env (never hardcode secrets here).
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
. "$root/scripts/_env.sh"
pw=$(sed -n 's/^steamos_root_pwd=//p' "$root/.env" 2>/dev/null || true)
pw=${pw#[\"\']}; pw=${pw%[\"\']}
if [ -z "$pw" ]; then
  echo "no steamos_root_pwd in $root/.env" >&2
  exit 1
fi
echo "pw_len=${#pw}"
if printf '%s\n' "$pw" | ssh -o BatchMode=yes "$FRAME_HOST" "sudo -S -p '' true"; then
  echo SUDO_OK
else
  echo SUDO_REJECTED >&2
  exit 1
fi
