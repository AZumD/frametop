#!/usr/bin/env bash
# Dump nested plasmashell.env display keys + X11 sockets for ft-game-run design.
set -u
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
set +e
f=/run/user/1000/frametop/plasmashell.env
echo "=== plasmashell.env keys ==="
if [ -f "$f" ]; then
  tr '\0' '\n' < "$f" | grep -E '^(DISPLAY|WAYLAND_DISPLAY|XDG_RUNTIME_DIR|DBUS_SESSION_BUS_ADDRESS|XAUTHORITY|XDG_SESSION_TYPE)=' || true
else
  echo "MISSING $f"
fi
echo
echo "=== X11 sockets ==="
ls -la /tmp/.X11-unix/ 2>/dev/null || true
echo
echo "=== xauth files ==="
ls -la /run/user/1000/frametop/xauth* 2>/dev/null || true
echo
echo "=== desktop up? ==="
pgrep -x plasmashell >/dev/null && echo plasmashell=yes || echo plasmashell=no
pgrep -x kwin_wayland >/dev/null && echo kwin=yes || echo kwin=no
EOF
