#!/usr/bin/env bash
# Probe Display Settings QML on the Frame (avoid nested SSH quoting).
set -euo pipefail
qml=~/dev/frametop/display-settings/main.qml
echo "qml=$(wc -c < "$qml") bytes mtime=$(stat -c %y "$qml")"
grep -n 'readonly property string key\|editSheet.key\|indexOf(editKey)\|id: editSheet\|Kirigami.Dialog\|OverlaySheet\|contentItem' "$qml" | head -40
echo '--- launchers ---'
ls -la ~/.local/share/applications/*[Dd]isplay* 2>/dev/null || true
grep -H . ~/.local/share/applications/*[Dd]isplay* 2>/dev/null | head -30 || true
echo '--- copies of main.qml ---'
find /home/steamos -name 'main.qml' 2>/dev/null | head
echo '--- ~/frametop vs ~/dev/frametop ---'
for p in /home/steamos/frametop/display-settings/main.qml /home/steamos/dev/frametop/display-settings/main.qml; do
  echo "== $p =="
  grep -n 'readonly property string key\|indexOf(editKey)\|id: editSheet' "$p" 2>/dev/null | head -8 || echo missing
done
echo '--- running display settings ---'
pgrep -af 'ft_display_settings|ft-display-settings' | head || true
