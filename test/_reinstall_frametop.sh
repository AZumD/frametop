#!/usr/bin/env bash
# Re-install Frametop on the Frame (non-interactive). No Bluetooth (needs sudo).
# SteamVR is left alone; start it later so ft_pointer / relay come up cleanly.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
. "$root/scripts/_env.sh"

echo "== sync + install.sh --yes --with-pointer =="
"$root/install.sh" --yes --with-pointer --no-bluetooth

echo "== verify =="
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
set +e
echo "launcher:"
grep -E '^Exec=' ~/.local/share/applications/deckard-nested-desktop.desktop 2>&1 | head -1
echo "units:"
for u in frametop-input-relay.service frametop-pointer.service; do
  echo "  $u: $(systemctl --user is-enabled $u 2>&1) / $(systemctl --user is-active $u 2>&1)"
done
echo "POINTER=$(grep ^POINTER= ~/.config/frametop.conf 2>/dev/null || echo unset)"
echo "driver: $(test -d ~/.local/share/frametop/ft_pointer && echo present || echo missing)"
echo "settings:"
ls ~/.local/share/applications/ft-display-settings.desktop ~/.local/share/applications/ft-input-settings.desktop 2>&1
EOF
echo DONE
