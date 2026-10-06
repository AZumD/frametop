#!/usr/bin/env bash
set -euo pipefail

echo "=== frame-autopass unit (info only) ==="
systemctl --user cat frame-autopass.service 2>&1 | head -50 || true

echo
echo "=== uninstall Frame Passthrough Shortcuts ==="
PTS="$HOME/devkit-game/Frame_Passthrough_Shortcuts/frame-passthrough-shortcuts"
if [ -f "$PTS" ]; then
  chmod +x "$PTS" \
    "$HOME/devkit-game/Frame_Passthrough_Shortcuts/frame-passthrough-control" 2>/dev/null || true
  "$PTS" --uninstall
  echo "exit: $?"
else
  echo "binary missing"
fi

rm -rf "$HOME/devkit-game/Frame_Passthrough_Shortcuts"
rm -f \
  "$HOME/devkit-game/Frame_Passthrough_Shortcuts-argv.json" \
  "$HOME/devkit-game/Frame_Passthrough_Shortcuts-settings.json"

echo
echo "=== leftover check ==="
ls "$HOME/devkit-game/" | grep -i passthrough || echo "no passthrough entries in devkit-game"
find "$HOME/.config/openvr" "$HOME/.local/share/Steam/steamapps/common" \
  -iname '*Frame_Passthrough*' 2>/dev/null | head -20 || true
