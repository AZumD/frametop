#!/usr/bin/env bash
# Copy spatial-toolbar sources from stage2 worktree into customized-main.
set -euo pipefail
SRC=/mnt/c/Users/Antho/Projects/frametop-stage1-chrome
DST=/mnt/c/Users/Antho/Projects/frametop-customized-main
files=(
  session/ft-taskbar.py
  layout/ft_toolbar.py
  layout/ft_taskbar_model.py
  screens/desktop_toolbar.inc
  screens/toolbar_dock.inc
  screens/toolbar_taskbar.inc
  screens/spatial.inc
  screens/steamvr_assets.h
  screens/steamvr_assets.cpp
  screens/assets/start-icon.png
  test/test_desktop_toolbar.py
  test/test_toolbar_dock.py
  test/test_taskbar_model.py
  docs/README/DESKTOP_TOOLBAR.md
  docs/README/FT-TASKBAR.md
  docs/README/FT_TASKBAR_MODEL.md
)
for f in "${files[@]}"; do
  mkdir -p "$(dirname "$DST/$f")"
  cp -a "$SRC/$f" "$DST/$f"
  echo "copied $f"
done
for f in docs/README/TEST_TOOLBAR_DOCK.md docs/README/TEST_TASKBAR_MODEL.md docs/README/TEST_DESKTOP_TOOLBAR.md; do
  if [ -f "$SRC/$f" ]; then
    cp -a "$SRC/$f" "$DST/$f"
    echo "copied $f"
  fi
done
echo DONE
ls -la "$DST/session/ft-taskbar.py" "$DST/screens/desktop_toolbar.inc" "$DST/layout/ft_toolbar.py"
