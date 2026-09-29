#!/bin/bash
# Locate SteamVR and any eyetracking / frame_hmd input definitions.
set -e
echo "=== steam dirs ==="
ls -la "$HOME/.steam" 2>/dev/null | head || true
ls -la "$HOME/.local/share/Steam" 2>/dev/null | head || true
echo "=== vrpathreg / openvrpaths ==="
cat "$HOME/.config/openvr/openvrpaths.vrpath" 2>/dev/null || cat "$HOME/.local/share/Steam/config/openvrpaths.vrpath" 2>/dev/null || true
echo "=== find frame_hmd ==="
for root in "$HOME/.steam" "$HOME/.local/share/Steam" /opt/steamvr /usr/lib/steam; do
  [ -e "$root" ] || continue
  find -L "$root" \( -iname '*frame*hmd*' -o -iname '*frame_hmd*' -o -iname '*eyetrack*' \) 2>/dev/null | head -40
done
echo "=== grep eyetracking in steamvr drivers (limited) ==="
VR=$(python3 -c "import json,os; p=os.path.expanduser('~/.config/openvr/openvrpaths.vrpath');
import pathlib
for c in [p, os.path.expanduser('~/.local/share/Steam/config/openvrpaths.vrpath')]:
  if os.path.isfile(c):
    d=json.load(open(c)); print('\n'.join(d.get('runtime',[])+d.get('config',[]))); break" 2>/dev/null || true)
echo "paths: $VR"
for r in $VR; do
  [ -d "$r" ] || continue
  echo "scanning $r"
  grep -r -l -i 'eyetrack\|/eyetracking' "$r" 2>/dev/null | head -20
  find "$r" -iname '*frame*' 2>/dev/null | head -30
done
