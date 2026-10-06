#!/usr/bin/env bash
set -euo pipefail
echo "=== keyboard in synced QML ==="
grep -n 'text: "Keyboard"' ~/dev/frametop/input-settings/main.qml || echo 'MISSING Keyboard action'
grep -n 'Open/close keyboard' ~/dev/frametop/input-settings/ft_input_settings.py || echo 'MISSING action label'
echo "=== desktop files ==="
ls ~/.local/share/applications/ | grep -iE 'frame|input' || true
for f in ~/.local/share/applications/*frametop* ~/.local/share/applications/*input* ~/.local/share/applications/*Input*; do
  [ -f "$f" ] || continue
  echo "==== $f ===="
  cat "$f"
done
