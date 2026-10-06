#!/usr/bin/env bash
# Write a tiny remote probe script to avoid nested-quote pain from Windows→WSL.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
. "$root/scripts/_env.sh"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
set -e
echo "getcap: $(getcap /home/steamos/dev/frametop/hands/build/ft-camd 2>&1 || true)"
echo "screens_active: $(systemctl --user is-active frametop-screens.service 2>&1 || true)"
bin=
for p in "$HOME/.local/bin/ft-screens" "$HOME/dev/frametop/screens/build/ft-screens"; do
  [ -x "$p" ] && bin=$p && break
done
echo "screens_bin=$bin"
if [ -n "$bin" ]; then
  strings "$bin" | grep -E 'cutouts|hand cutouts' | head -5 || echo "no cutouts strings"
fi
echo "ctl_link=$(readlink -f ~/.local/bin/ft-handsctl 2>&1 || true)"
EOF
