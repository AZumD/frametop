#!/usr/bin/env bash
# Uninstall Frametop from the Frame (README uninstall + hands extras).
# Does NOT restart SteamVR (needs user approval per AGENTS.md).
# Does NOT remove ~/dev/frametop checkout, distrobox, or ~/.config/frametop*.json.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
. "$root/scripts/_env.sh"

echo "FRAME_HOST=$FRAME_HOST"
if ! ssh -o BatchMode=yes -o ConnectTimeout=15 "$FRAME_HOST" 'hostname'; then
  echo "Frame unreachable over SSH — turn it on / wake it, then re-run." >&2
  exit 1
fi

echo "== stop Frametop desktop =="
"$root/desktops.sh" stop || true

echo "== hands =="
"$root/hands/run.sh" uninstall || true

echo "== pointer =="
"$root/pointer/helper/run.sh" uninstall || true
"$root/pointer/driver/install.sh" uninstall || true

echo "== relay + launcher desktop =="
"$root/desktops.sh" relay uninstall || true
"$root/desktops.sh" uninstall || true

echo "== settings apps =="
"$root/input-settings/install.sh" uninstall || true
"$root/display-settings/install.sh" uninstall || true

echo "== bluetooth (best-effort; may need sudo) =="
"$root/setup/bluetooth/install.sh" uninstall || true

echo "== leftover user units / launchers =="
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
set +e
systemctl --user disable --now frametop-camd.service frametop-hands.service \
  frametop-gaze.service frametop-pointer.service frametop-input-relay.service 2>/dev/null
systemctl --user stop frametop-desktop.service 2>/dev/null
rm -f ~/.config/systemd/user/frametop-*.service \
      ~/.config/systemd/user/default.target.wants/frametop-*.service \
      ~/.config/systemd/user/steamvr.service.wants/frametop-*.service
systemctl --user daemon-reload
rm -f ~/.local/share/applications/deckard-nested-desktop.desktop \
      ~/.local/share/applications/ft-display-settings.desktop \
      ~/.local/share/applications/ft-input-settings.desktop \
      ~/.local/share/applications/ft-gazeprobe.desktop \
      ~/.local/share/applications/ft-gaze-probe.desktop \
      ~/.local/bin/ft-handsctl
# Optional: clear POINTER so stock SteamVR isn't looking for the helper
if [ -f ~/.config/frametop.conf ]; then
  sed -i 's/^POINTER=1/POINTER=0/' ~/.config/frametop.conf
fi
echo "--- remaining frametop units ---"
systemctl --user list-unit-files --no-pager 2>/dev/null | grep -i frametop || echo "(none)"
echo "--- remaining launchers ---"
ls ~/.local/share/applications/*frametop* ~/.local/share/applications/ft-* \
   ~/.local/share/applications/deckard-nested* 2>/dev/null || echo "(none)"
echo "--- driver dir ---"
ls ~/.local/share/frametop 2>/dev/null || echo "(no ~/.local/share/frametop)"
EOF

echo
echo "Frametop uninstall finished on $FRAME_HOST."
echo "Stock SteamOS 'Desktop' launcher should be back."
echo "SteamVR was NOT restarted — restart it once if the optional ft_pointer driver was loaded."
echo "Repo checkout ~/dev/frametop and layout/profile configs were left in place."
