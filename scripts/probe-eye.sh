#!/bin/bash
set -e
echo "=== screens log eye lines ==="
grep -a -iE 'eye|gaze|manifest|IVRInput' /tmp/frametop-screens.log 2>/dev/null | tail -40 || true
echo "=== actions.json next to binary ==="
EXE=$(readlink -f /proc/$(pgrep -nx ft-screens)/exe 2>/dev/null || true)
echo "EXE=$EXE"
if [ -n "$EXE" ]; then ls -la "$(dirname "$EXE")/actions.json" 2>&1; fi
echo "=== search eye in steam input profiles ==="
for root in "$HOME/.steam/steam" "$HOME/.local/share/Steam" "/usr/lib/steam" "/home/steamos/.steam"; do
  [ -d "$root" ] || continue
  find "$root" -name '*profile.json' 2>/dev/null | while read -r f; do
    if grep -qi eye "$f" 2>/dev/null; then echo "$f"; grep -i eye "$f" | head -5; fi
  done
done | head -60
echo "=== frame_hmd / eyetracking paths ==="
find "$HOME" -path '*input*' -name '*frame*' 2>/dev/null | head -40
