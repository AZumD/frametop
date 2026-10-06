#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/Antho/Projects/frametop-customized-main
python3 test/test_float_cross_panel_dnd.py
python3 test/test_float_phase3.py
git diff --check -- pointer/helper/ft-pointer.cpp screens/compositor.c screens/vr.cpp \
  test/test_float_cross_panel_dnd.py docs/README/FT_POINTER.md docs/README/FT_FLOATD.md
scripts/sync.sh
scripts/frame.sh -C screens './build.sh'
scripts/frame.sh -C pointer/helper './build.sh'
scripts/frame.sh --host 'bash -s' <<'EOF'
pkill -x ft-pointer 2>/dev/null || true
sleep 1
pgrep -a ft-pointer || true
pgrep -a ft-screens || true
echo "Restart the Frametop desktop to load the new ft-screens binary."
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
