#!/usr/bin/env bash
set -eu

echo "=== remove remaining steam-frame-nix / home-manager user files ==="
rm -f \
  "$HOME/.config/environment.d/10-home-manager.conf" \
  "$HOME/.config/autostart/clipboard-sync.desktop" \
  "$HOME/.local/share/icons/hicolor/scalable/apps/preferences-system.svg" \
  "$HOME/.local/share/icons/hicolor/scalable/apps/utilities-terminal.svg"

rm -rf "$HOME/.local/share/xdg-desktop-portal/gamescope-portals"

# steam-frame-nix stashed profiles under this path; do NOT wipe all of ~/.local/state/frametop
rm -rf \
  "$HOME/.local/state/frametop/nix" \
  "$HOME/.local/state/frametop/home-manager"

rmdir "$HOME/.config/environment.d" 2>/dev/null || true
rmdir "$HOME/.config/systemd/user/xdg-desktop-portal.service.d" 2>/dev/null || true
# keep steamvr.service.d (has asterism-shell-redirect.conf from elsewhere)

systemctl --user daemon-reload || true

echo "=== remaining links into /nix/store under home ==="
find "$HOME" -lname '*/nix/store/*' 2>/dev/null | head -50 || echo none

echo "=== /nix presence ==="
ls /nix/nix-installer /nix/receipt.json 2>/dev/null || echo "/nix installer gone"
df -h /nix 2>/dev/null | head || true
du -sh /home/nix 2>/dev/null || true