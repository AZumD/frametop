#!/usr/bin/env bash
# Uninstall Frame Passthrough Shortcuts and steam-frame-nix from the Frame.
set -euo pipefail

echo "=== frame-autopass unit (info only; not removing) ==="
systemctl --user status frame-autopass.service --no-pager 2>&1 | head -25 || true
systemctl --user cat frame-autopass.service 2>&1 | head -40 || true

echo
echo "=== 1) Frame Passthrough Shortcuts ==="
PTS="$HOME/devkit-game/Frame_Passthrough_Shortcuts/frame-passthrough-shortcuts"
if [ -f "$PTS" ]; then
  chmod +x "$PTS" "$HOME/devkit-game/Frame_Passthrough_Shortcuts/frame-passthrough-control" 2>/dev/null || true
  "$PTS" --uninstall
  echo "passthrough --uninstall exit: $?"
else
  echo "passthrough binary missing; cleaning leftover dirs if any"
fi

# Remove package tree / FrameDrop sidecar files if uninstall left them
rm -rf "$HOME/devkit-game/Frame_Passthrough_Shortcuts"
rm -f \
  "$HOME/devkit-game/Frame_Passthrough_Shortcuts-argv.json" \
  "$HOME/devkit-game/Frame_Passthrough_Shortcuts-settings.json"
echo "passthrough package tree removed (if present)"

echo
echo "=== 2) steam-frame-nix ==="
# Official uninstall: cleanup --all, home-manager uninstall, then remove Nix.
# --yes answers prompts. Needs sudo (steamos root password via askpass/.env if set).
if [ -x /nix/nix-installer ] || [ -d /nix/store ] || [ -d "$HOME/nix-config" ]; then
  curl -fsSL https://steam-frame-nix.lhns.de | bash -s -- uninstall --yes
  echo "steam-frame-nix uninstall exit: $?"
else
  echo "no steam-frame-nix / nix install detected"
fi

echo
echo "=== post-check ==="
echo -n "Frame_Passthrough_Shortcuts dir: "
[ -e "$HOME/devkit-game/Frame_Passthrough_Shortcuts" ] && echo STILL_PRESENT || echo gone
echo -n "/nix: "
[ -e /nix ] && echo STILL_PRESENT || echo gone
echo -n "~/nix-config: "
[ -e "$HOME/nix-config" ] && echo STILL_PRESENT || echo gone
systemctl --user list-units --all 2>/dev/null | grep -iE 'steam-frame|steamvr-webhelper-debugger|passthrough-shortcuts' || echo "(no steam-frame/passthrough-shortcuts units)"
