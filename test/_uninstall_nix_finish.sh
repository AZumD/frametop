#!/usr/bin/env bash
# Finish removing steam-frame-nix's Nix install (/nix, /home/nix) on the Frame.
# Requires steamos_root_pwd in the repo .env (gitignored; never synced).
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
. "$root/scripts/_env.sh"

pw=$(sed -n 's/^steamos_root_pwd=//p' "$root/.env" 2>/dev/null || true)
pw=${pw#[\"\']}; pw=${pw%[\"\']}
if [ -z "$pw" ]; then
  echo "no steamos_root_pwd in $root/.env" >&2
  echo "Add: steamos_root_pwd=\"<password>\"" >&2
  exit 1
fi

echo "== pre-check =="
ssh -o BatchMode=yes "$FRAME_HOST" 'ls -la /nix/nix-installer /nix/receipt.json /home/nix 2>&1 | head -20; findmnt /nix || true'

if ! ssh -o BatchMode=yes "$FRAME_HOST" 'test -x /nix/nix-installer'; then
  if ssh -o BatchMode=yes "$FRAME_HOST" 'test -e /nix || test -e /home/nix'; then
    echo "ERROR: /nix or /home/nix present but nix-installer missing" >&2
    exit 1
  fi
  echo "nix already gone"
  exit 0
fi

echo "== nix-installer uninstall =="
# Password on sudo's stdin only (never on the command line).
printf '%s\n' "$pw" | ssh -o BatchMode=yes "$FRAME_HOST" \
  "sudo -S -p '' /nix/nix-installer uninstall --no-confirm"

echo "== post-check =="
ssh -o BatchMode=yes "$FRAME_HOST" '
if [ -e /nix ] || [ -e /home/nix ]; then
  echo "WARNING: /nix or /home/nix still present" >&2
  findmnt /nix 2>/dev/null || true
  ls -la /nix /home/nix 2>&1 | head || true
  exit 1
fi
echo "VERIFY_OK: /nix and /home/nix gone"
'
