#!/usr/bin/env bash
# Confirm Frame is running the synced ~/dev/frametop tree (not stale ~/frametop).
set -euo pipefail
dev=$HOME/dev/frametop
echo "=== launchers ==="
grep '^Exec=' ~/.local/share/applications/ft-display-settings.desktop
grep '^Exec=' ~/.local/share/applications/deckard-nested-desktop.desktop 2>/dev/null || echo '(no deckard desktop entry)'
echo "=== running ft-screens ==="
pgrep -a ft-screens | head -3 || echo '(not running)'
exe=$(readlink -f /proc/$(pgrep -x ft-screens | head -1)/exe 2>/dev/null || true)
echo "exe=$exe"
echo "=== display-settings syntax ==="
python3 -m py_compile "$dev/display-settings/ft_display_settings.py" && echo compile_ok
echo "=== qml load ==="
bash "$dev/test/probe_qml_load_on_frame.sh" 2>&1 | grep -E '^roots |Property value|SyntaxError|Error:' || true
echo "=== file fingerprints ==="
md5sum "$dev/display-settings/ft_display_settings.py" "$dev/display-settings/main.qml" "$dev/screens/build/ft-screens" 2>/dev/null || true
if [ -f "$HOME/frametop/display-settings/ft_display_settings.py" ]; then
  echo "--- stale ~/frametop copy (should match or be unused) ---"
  md5sum "$HOME/frametop/display-settings/ft_display_settings.py" 2>/dev/null || true
  cmp -s "$dev/display-settings/ft_display_settings.py" "$HOME/frametop/display-settings/ft_display_settings.py" && echo frametop_settings_MATCH || echo frametop_settings_STALE
fi
