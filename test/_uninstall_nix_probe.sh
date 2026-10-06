#!/usr/bin/env bash
set -eu
echo "sudo -n true?"; if sudo -n true 2>/dev/null; then echo YES; else echo NO; fi
echo "SUDO_ASKPASS=${SUDO_ASKPASS:-}"
ls -la /etc/sudoers.d 2>/dev/null | head || true
echo "nix mount:"; findmnt /nix 2>/dev/null || true
echo "home/nix:"; ls -la /home/nix 2>/dev/null | head || echo "no /home/nix"
echo "steamvr-webhelper unit:";
systemctl --user cat steamvr-webhelper-debugger.service 2>&1 | head -30 || true
ls -la "$HOME/.config/systemd/user/"*steamvr* "$HOME/.config/systemd/user/"*steam-frame* 2>/dev/null || true
echo "nix-config:"; ls -la "$HOME/nix-config" 2>/dev/null | head -20 || true
# Can we source nix profile somehow?
ls "$HOME/.nix-profile" 2>/dev/null || echo "no .nix-profile"
ls /nix/var/nix/profiles/per-user/steamos 2>/dev/null || echo "no per-user profiles"
