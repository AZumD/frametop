#!/usr/bin/env bash
# Finish hands install bits that do not need root (units + PATH link).
# setcap still needs: hands/run.sh caps  (TTY password or steamos_root_pwd in .env)
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
. "$root/scripts/_env.sh"
units="frametop-camd.service frametop-hands.service"

echo "installing user units + ~/.local/bin/ft-handsctl on Frame…"
for u in $units; do
  fill_template "$root/hands/$u" | on_frame "mkdir -p ~/.config/systemd/user && cat > ~/.config/systemd/user/$u"
done
"$root/scripts/frame.sh" --host "set -e
systemctl --user daemon-reload
systemctl --user disable $units 2>/dev/null || true
mkdir -p ~/.local/bin
ln -sfn $(printf %q "$FRAME_REPO/hands/ft-handsctl") ~/.local/bin/ft-handsctl
for u in $units; do echo \"\$u: \$(systemctl --user is-enabled \$u 2>&1) / \$(systemctl --user is-active \$u 2>&1)\"; done
echo link=\$(readlink ~/.local/bin/ft-handsctl)
"
echo "next (needs sudo once): hands/run.sh caps"
echo "then: ./hands/ft-handsctl on"
