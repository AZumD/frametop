#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/Antho/Projects/frametop-customized-main
python3 test/test_float_cross_panel_dnd.py
python3 test/test_float_phase3.py
python3 test/test_pointer_ignore.py
git diff --check
scripts/sync.sh
scripts/frame.sh -C screens './build.sh'
scripts/frame.sh -C pointer/helper './build.sh'
# Restart helper so the new binary is used (do not kill gamescope/steam/vrserver).
scripts/frame.sh --host 'bash -s' <<'EOF'
set -e
pkill -x ft-pointer 2>/dev/null || true
# frametop-pointer.service usually respawns; if not, start the helper once.
sleep 1
if ! pgrep -x ft-pointer >/dev/null; then
  nohup /home/steamos/dev/frametop/pointer/helper/build/ft-pointer >/tmp/frametop-pointer.log 2>&1 &
fi
# ft-screens is owned by the desktop session — ask user to restart desktop, or try soft replace
# only if a simple exec path exists. Prefer desktop restart for compositor.c changes.
echo "ft-pointer: $(pgrep -a ft-pointer || echo none)"
echo "ft-screens: $(pgrep -a ft-screens || echo none)"
echo "NOTE: restart the Frametop desktop so ft-screens loads the new compositor (x+1/clear-focus + catcher)."
EOF

cat > /tmp/ft_dnd2_msg.txt <<'EOF'
Fix soft-follow killing cross-panel drag retarget

Our follow modes move panel poses every frame; the 0.001 matrix still-check
cleared pressKey immediately so the 3D mouse never retargeted onto another
FramePanel. Use a 5 cm carry threshold, always intersect FramePanels while
held, prefer the nearest catcher hit, and clear seat focus before cross-panel
enter.
EOF
git add pointer/helper/ft-pointer.cpp screens/compositor.c screens/vr.cpp \
  docs/README/FT_POINTER.md docs/README/FT_FLOATD.md test/test_float_cross_panel_dnd.py
git diff --cached --stat
git commit -F /tmp/ft_dnd2_msg.txt
git log -1 --oneline
