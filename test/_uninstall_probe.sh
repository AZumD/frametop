#!/usr/bin/env bash
set -euo pipefail

echo "=== passthrough ==="
if [ -d "$HOME/devkit-game/Frame_Passthrough_Shortcuts" ]; then
  ls -la "$HOME/devkit-game/Frame_Passthrough_Shortcuts"
  if [ -x "$HOME/devkit-game/Frame_Passthrough_Shortcuts/frame-passthrough-shortcuts" ]; then
    echo "binary present"
  fi
else
  echo "no Frame_Passthrough_Shortcuts dir"
fi
echo "devkit-game entries:"
ls "$HOME/devkit-game/" 2>/dev/null || echo "(no devkit-game)"

echo
echo "=== nix / steam-frame-nix ==="
if [ -d /nix ]; then
  ls -la /nix | head -20
else
  echo "no /nix"
fi
command -v nix || echo "nix not on PATH"
command -v home-manager || echo "home-manager not on PATH"
command -v steam-frame-nix-cleanup || echo "steam-frame-nix-cleanup not on PATH"
for p in \
  "$HOME/.config/home-manager" \
  "$HOME/nix-config" \
  "$HOME/.local/state/home-manager" \
  "$HOME/.local/state/nix" \
  "$HOME/.local/state/steam-frame-nix" \
  "$HOME/.config/nix"
do
  if [ -e "$p" ]; then
    echo "EXISTS $p -> $(readlink -f "$p" 2>/dev/null || echo "$p")"
  else
    echo "missing $p"
  fi
done
if [ -f /nix/receipt.json ]; then
  echo "receipt exists"
elif [ -f /nix/nix-installer ]; then
  echo "nix-installer present, no receipt.json"
else
  echo "no receipt / nix-installer"
fi

echo
echo "=== user units (nix/passthrough/steam-frame) ==="
systemctl --user list-units --all 2>/dev/null | grep -iE 'nix|home-manager|passthrough|steam-frame' || echo "(none)"
ls "$HOME/.config/systemd/user/" 2>/dev/null | grep -iE 'nix|home|passthrough|steam-frame' || echo "(no matching unit files)"

echo
echo "=== openvr / steamvr apps ==="
find "$HOME/.local/share/Steam" "$HOME/.steam" "$HOME/.config/openvr" \
  -iname '*passthrough*' 2>/dev/null | head -40 || true
find "$HOME/devkit-game" -maxdepth 2 -type f -iname '*passthrough*' 2>/dev/null || true
