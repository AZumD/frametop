#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/Antho/Projects/frametop-customized-main
scripts/frame.sh --host 'bash -s' <<'EOF'
set -e
echo "=== enter fix in source ==="
grep -n 'notify_enter.*x + 1\|Entering one unit\|cross-panel DnD' ~/dev/frametop/screens/compositor.c || true
echo "=== FramePanel in pointer source ==="
grep -n 'FramePanel\|pressKey\|ft_screens\", \"up\"' ~/dev/frametop/pointer/helper/ft-pointer.cpp | head -20
echo "=== process start times ==="
ps -o pid,lstart,etime,cmd -C ft-screens -C ft-pointer -C ft-floatd 2>/dev/null || true
echo "=== binary strings (running image) ==="
# confirm x+1 comment or nearby unique string is in the ELF
strings ~/dev/frametop/screens/build/ft-screens | grep -F 'cross-panel DnD' || echo 'MISSING cross-panel string in binary'
strings ~/dev/frametop/pointer/helper/build/ft-pointer | grep -F 'Across Frametop' || echo 'MISSING Across Frametop in pointer binary'
echo "=== recent screens/floatd logs (dnd-ish) ==="
grep -E 'caught a release|float |unfloat |FocusLeave|carry' /tmp/frametop-screens.log 2>/dev/null | tail -30 || true
tail -20 /tmp/frametop-floatd.log 2>/dev/null || true
EOF
