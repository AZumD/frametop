#!/usr/bin/env bash
set -uo pipefail
cd /mnt/c/Users/Antho/Projects/frametop-customized-main || exit 1

echo "=== working tree vs stage2 tip ==="
for f in screens/vr.cpp screens/desktop_toolbar.inc screens/toolbar_taskbar.inc screens/toolbar_dock.inc layout/ft_toolbar.py session/ft-taskbar.py layout/ft_desktop.py; do
  if [ ! -f "$f" ]; then echo "-- $f MISSING"; continue; fi
  if ! git cat-file -e "stage2-desktop-toolbar:$f" 2>/dev/null; then echo "-- $f not on stage2"; continue; fi
  git show "stage2-desktop-toolbar:$f" > /tmp/stage2_cmp
  lines=$(diff -u /tmp/stage2_cmp "$f" | wc -l)
  echo "-- $f diff_lines=$lines"
done

echo
echo "=== key markers in working tree ==="
echo "-- MakeChrome mouse scale"
awk '/VROverlayHandle_t MakeChrome/,/^}/' screens/vr.cpp | grep -n SetOverlayMouseScale || echo MISSING_IN_MAKECHROME

echo "-- DestroyToolbarCells / keep backing"
grep -n "DestroyToolbarCells\|RebuildToolbarForTasks\|DestroyToolbarOverlays" screens/desktop_toolbar.inc | head

echo "-- OnlyShowIn / Hidden Start"
grep -nE "OnlyShowIn|NoDisplay|Hidden|launchable|gamescope" session/ft-taskbar.py layout/ft_desktop.py 2>/dev/null | head -30

echo "-- kCellBandNudge / icon paint offset"
grep -nE "kCellBandNudge|CellBandNudge|paint.*offset|TexOffset|glyph.*2" screens/desktop_toolbar.inc layout/ft_toolbar.py | head

echo "-- task right-click menu"
grep -nE "right.?click|context.?menu|Send to desktop|task_menu|TaskMenu" session/ft-taskbar.py screens/toolbar_taskbar.inc 2>/dev/null | head

echo "-- strip CR on sync"
grep -nE "dos2unix|CRLF|\\\\r|fix_crlf|strip.*CR" scripts/sync.sh test/_fix_crlf_tree.py 2>/dev/null | head

echo "-- resize handle corner"
grep -nE "CornerTexture|bottom.right|ControlOffsets|handle" screens/vr.cpp | head -25

echo "-- ChromeStyle SoftOutline / Pill"
grep -nE "SoftOutline|PillTexture|ChromeStyle::" screens/vr.cpp | head -25
