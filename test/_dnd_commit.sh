#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/Antho/Projects/frametop-customized-main
git add screens/compositor.c pointer/helper/ft-pointer.cpp \
  docs/README/FT_FLOATD.md docs/README/FT_POINTER.md \
  docs/README/SCREENS_TEST_HEADLESS.md test/test_float_cross_panel_dnd.py
cat > /tmp/ft_commit_msg.txt <<'EOF'
Fix cross-panel drag and drop

Enter a new panel one seat unit off so the following motion is not dropped
by wlroots; without that, KWin kept the old output mid-drag across gaps.
EOF
git commit -F /tmp/ft_commit_msg.txt
git log -1 --format='%H %s'
git status --short | head -25
