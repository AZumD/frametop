#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/Antho/Projects/frametop-customized-main
scripts/frame.sh --host 'bash -s' <<'EOF'
set -e
echo "=== processes ==="
pgrep -a ft-screens || true
pgrep -a ft-pointer || true
pgrep -a ft-floatd || true
echo "=== binaries ==="
ls -la ~/dev/frametop/screens/build/ft-screens ~/dev/frametop/pointer/helper/build/ft-pointer 2>&1
echo "=== x+1 in deployed source ==="
grep -n 'x + 1' ~/dev/frametop/screens/compositor.c | head -5 || true
echo "=== running binary vs build mtime ==="
ps -o pid,lstart,cmd -C ft-screens 2>/dev/null || true
stat -c '%y %n' ~/dev/frametop/screens/build/ft-screens 2>/dev/null || true
EOF
