#!/usr/bin/env bash
set -u
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
set +e
export XDG_RUNTIME_DIR=/run/user/$(id -u)
repo=/home/steamos/dev/frametop
bin=$repo/screens/build/ft-screens

echo "=== file / mtime ==="
ls -la "$bin"
stat -c '%y' "$bin"

echo "=== distrobox: print argv via wrapper ==="
"$HOME/.local/bin/distrobox" enter dev -- bash -lc 'printf "ARG<%s>\n" "$@"' -- \
  "$bin" --socket ft-screens-0 --screen 1920x1080@1.940 --screen 2616x1080@0.947 --spares 8

echo "=== distrobox: run with explicit args, capture exit ==="
: > /tmp/frametop-screens.log
"$HOME/.local/bin/distrobox" enter dev -- "$bin" \
  --socket ft-screens-0 \
  --screen '1920x1080@1.940' \
  --screen '2616x1080@0.947' \
  --spares 8 > /tmp/frametop-screens.log 2>&1 &
pid=$!
sleep 3
if pgrep -x ft-screens >/dev/null; then
  echo RUNNING
  pgrep -ax ft-screens | head -3
  pkill -x ft-screens || true
else
  echo EXITED
  wait $pid; echo exit=$?
  cat /tmp/frametop-screens.log
fi

echo "=== strings usage from binary ==="
strings "$bin" | grep -F 'usage:' | head -3

echo "=== rebuild in distrobox? ==="
# Check if binary is actually the screens one
"$HOME/.local/bin/distrobox" enter dev -- nm -D "$bin" 2>/dev/null | grep -i spare | head || true
"$HOME/.local/bin/distrobox" enter dev -- bash -lc "cd $repo/screens && head -5 Makefile 2>/dev/null; ls build/"
EOF
