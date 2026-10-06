#!/usr/bin/env bash
set -eu
echo "=== remaining HM/nix user files ==="
ls -la "$HOME/.config/environment.d" 2>/dev/null || true
ls -la "$HOME/.config/autostart/clipboard-sync.desktop" 2>/dev/null || true
ls -la "$HOME/.local/state/frametop/nix" 2>/dev/null | head -20 || echo "no frametop nix state"
readlink -f "$HOME/.local/state/frametop/nix/profiles/profile" 2>/dev/null || true
ls -la "$HOME/.local/state/frametop/nix/profiles" 2>/dev/null | head || true
echo "=== other nix links in home (depth 4) ==="
find "$HOME/.config" "$HOME/.local" "$HOME/.cache" -lname '*/nix/store/*' 2>/dev/null | head -80 || true
echo "=== portal drop-ins ==="
ls -la "$HOME/.config/systemd/user/xdg-desktop-portal.service.d" 2>/dev/null || echo "gone"
ls -la "$HOME/.config/systemd/user/steamvr.service.d" 2>/dev/null || echo "steamvr.d gone or leftover"
echo "=== frametop units still ok? ==="
systemctl --user is-enabled frametop-pointer.service frametop-input-relay.service 2>&1 || true
pgrep -a ft-pointer || true
pgrep -a ft-screens || true