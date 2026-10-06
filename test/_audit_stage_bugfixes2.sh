#!/usr/bin/env bash
set -uo pipefail
cd /mnt/c/Users/Antho/Projects/frametop-customized-main || exit 1

echo "=== 6bc26d0 resize handle patch vs working tree ==="
git show 6bc26d0 -- screens/vr.cpp > /tmp/resize.patch
# Show what the commit changed that might be missing
git show 6bc26d0 --format="" -- screens/vr.cpp | grep -E '^[+-].*[Hh]andle|[+-].*Corner|[+-].*grip|[+-].*bottom|[+-].*ControlOffsets|[+-].*OnSurface' | head -60

echo
echo "=== ae2fe6a chrome language key hunks ==="
git show ae2fe6a --format="" -- screens/vr.cpp | grep -E '^[+-].*(ChromeStyle|PillTexture|SoftOutline|kIdle|BarTexture|CornerTexture|DigitTexture)' | head -80

echo
echo "=== 0dc2f4c OnlyShowIn / Start menu ==="
git show 0dc2f4c --stat --format="%s"
git show 0dc2f4c --format="" -- layout/ft_desktop.py session/ft-taskbar.py | head -120

echo
echo "=== 3c15206 sync CRLF ==="
git show 3c15206 --stat --format="%s"
git show 3c15206 --format="" | head -80

echo
echo "=== 54bde43 vanishing toolbar — already in tree? ==="
git show 54bde43 --format="" -- screens/desktop_toolbar.inc | grep -E '^[+-].*(DestroyToolbarCells|RebuildToolbar|backing)' | head -40

echo
echo "=== stage2 vr.cpp MakeChrome vs working ==="
git show stage2-desktop-toolbar:screens/vr.cpp | awk '/VROverlayHandle_t MakeChrome/,/^}/' > /tmp/s2_makechrome
awk '/VROverlayHandle_t MakeChrome/,/^}/' screens/vr.cpp > /tmp/wt_makechrome
diff -u /tmp/s2_makechrome /tmp/wt_makechrome || true

echo
echo "=== stage2 vs working ControlOffsets / CornerTexture ==="
git show stage2-desktop-toolbar:screens/vr.cpp | awk '/std::vector<Mat> ControlOffsets/,/^}/' > /tmp/s2_co
awk '/std::vector<Mat> ControlOffsets/,/^}/' screens/vr.cpp > /tmp/wt_co
echo "ControlOffsets diff:"; diff -u /tmp/s2_co /tmp/wt_co | head -80 || true

git show stage2-desktop-toolbar:screens/vr.cpp | awk '/std::vector<uint8_t> CornerTexture/,/^}/' > /tmp/s2_ct
awk '/std::vector<uint8_t> CornerTexture/,/^}/' screens/vr.cpp > /tmp/wt_ct
echo "CornerTexture diff:"; diff -u /tmp/s2_ct /tmp/wt_ct | head -80 || true

echo
echo "=== sync.sh CRLF handling ==="
grep -nE 'CRLF|dos2unix|\\\\r|fix.crlf|text' scripts/sync.sh || echo 'no CRLF in sync.sh'
ls test/_fix_crlf_tree.py 2>/dev/null && head -30 test/_fix_crlf_tree.py
