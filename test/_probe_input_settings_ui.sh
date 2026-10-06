#!/usr/bin/env bash
# Diagnose which Input Settings binary/QML the Frame is actually using.
set -euo pipefail
echo "=== desktop ==="
if [ -f ~/.local/share/applications/ft-input-settings.desktop ]; then
  cat ~/.local/share/applications/ft-input-settings.desktop
else
  echo "MISSING ~/.local/share/applications/ft-input-settings.desktop"
fi
echo
echo "=== synced repo keyboard markers ==="
qml=~/dev/frametop/input-settings/main.qml
py=~/dev/frametop/input-settings/ft_input_settings.py
for f in "$qml" "$py" ~/dev/frametop/input-settings/ft-input-settings; do
  echo "-- $f"
  ls -la "$f" 2>&1 || true
done
echo
grep -n 'text: "Keyboard"' "$qml" || echo "NO Keyboard in synced main.qml"
grep -n 'text: "Ignored panels"' "$qml" || echo "NO Ignored panels in synced main.qml"
grep -n 'keyboard_toggle' "$py" || echo "NO keyboard_toggle in synced py"
echo
echo "=== other frametop checkouts? ==="
ls -la ~/frametop/input-settings/main.qml 2>/dev/null || true
ls -la ~/dev/frametop/input-settings/main.qml 2>/dev/null || true
if [ -f ~/frametop/input-settings/main.qml ]; then
  echo "--- ~/frametop Keyboard ---"
  grep -n 'text: "Keyboard"' ~/frametop/input-settings/main.qml || echo "NO Keyboard in ~/frametop"
fi
echo
echo "=== running input-settings? ==="
pgrep -af 'ft.input|ft_input|input-settings' || true
echo
echo "=== head of synced main.qml actions ==="
sed -n '15,30p' "$qml"
