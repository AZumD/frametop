#!/usr/bin/env bash
set -euo pipefail

echo "=== nix-related user leftovers before ==="
ls -la "$HOME/.nix-profile" 2>/dev/null | head -5 || echo "no .nix-profile"
find "$HOME/.config/systemd/user" -lname '*/nix/store/*' 2>/dev/null || true
find "$HOME" -maxdepth 3 -lname '*/nix/store/*' 2>/dev/null | head -50 || true
ls -la "$HOME/.config/environment.d" 2>/dev/null || true
grep -n nix "$HOME/.bashrc" "$HOME/.bash_profile" "$HOME/.profile" 2>/dev/null || true

echo
echo "=== remove home-manager unit links into /nix/store ==="
# Only remove broken/HM links that point into the nix store under systemd user config
while IFS= read -r -d '' f; do
  echo "removing $f -> $(readlink "$f")"
  rm -f "$f"
done < <(find "$HOME/.config/systemd/user" -lname '*/nix/store/*' -print0 2>/dev/null)

# Drop empty wants/drop-in dirs only if empty after
rmdir "$HOME/.config/systemd/user/steamvr.service.d" 2>/dev/null || true

systemctl --user daemon-reload || true

echo
echo "=== .nix-profile ==="
if [ -L "$HOME/.nix-profile" ]; then
  echo "removing symlink $HOME/.nix-profile -> $(readlink "$HOME/.nix-profile")"
  rm -f "$HOME/.nix-profile"
elif [ -d "$HOME/.nix-profile" ]; then
  echo "WARNING: .nix-profile is a directory, not removing automatically"
  ls -la "$HOME/.nix-profile" | head
fi

# Common HM/Nix user state (safe; official uninstall removes these)
rm -rf \
  "$HOME/.local/state/home-manager" \
  "$HOME/.local/state/nix" \
  "$HOME/.local/state/steam-frame-nix" \
  "$HOME/.cache/nix" \
  "$HOME/.config/nix" \
  "$HOME/.config/home-manager"

# Keep ~/nix-config unless we remove it explicitly below (official uninstall keeps it).
# User asked to uninstall steam-frame-nix; remove the template/config dir too.
if [ -d "$HOME/nix-config" ]; then
  echo "removing ~/nix-config"
  rm -rf "$HOME/nix-config"
fi

echo
echo "=== after user cleanup ==="
find "$HOME/.config/systemd/user" -lname '*/nix/store/*' 2>/dev/null || echo "no systemd nix links"
ls -la "$HOME/.nix-profile" 2>/dev/null || echo ".nix-profile gone"
ls -la "$HOME/nix-config" 2>/dev/null || echo "nix-config gone"
systemctl --user list-units --all 2>/dev/null | grep -iE 'steamvr-webhelper|steam-frame' || echo "no steam-frame units"
echo
echo "=== /nix still needs sudo ==="
ls -la /nix/nix-installer /nix/receipt.json 2>/dev/null || true
if sudo -n true 2>/dev/null; then
  echo "passwordless sudo available; running nix-installer uninstall"
  sudo /nix/nix-installer uninstall --no-confirm
else
  echo "NO passwordless sudo. Put steamos_root_pwd in repo .env to finish removing /nix"
fi