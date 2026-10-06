#!/usr/bin/env bash
set -eu
echo "passthrough:"; ls "$HOME/devkit-game" | grep -i pass || echo gone
echo ".keep targets:"
ls -la "$HOME/.local/state/.keep" "$HOME/.cache/.keep" 2>/dev/null || true
readlink -f "$HOME/.local/state/.keep" "$HOME/.cache/.keep" 2>/dev/null || true
echo "nix mount still:"; findmnt /nix || echo "not mounted"
echo "groups:"; id