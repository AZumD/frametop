#!/usr/bin/env bash
set -u
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
set +e
export XDG_RUNTIME_DIR=/run/user/$(id -u)
repo=/home/steamos/dev/frametop
cd "$repo"

echo "=== procs ==="
pgrep -af 'ft-screens|ft-taskbar|ft-launch' | head -10

echo "=== files ==="
test -f session/ft-taskbar.py && echo has_ft_taskbar=yes || echo has_ft_taskbar=no
grep -c taskbar session/frametop-session.sh 2>/dev/null || echo 0

echo "=== ft-screens age vs build ==="
pid=$(pgrep -x ft-screens || true)
if [ -n "$pid" ]; then
  stat -c "proc_start %y" /proc/$pid
  readlink -f /proc/$pid/exe || true
fi
stat -c "build_mtime %y" screens/build/ft-screens 2>/dev/null || true
strings screens/build/ft-screens 2>/dev/null | grep -F 'frametop.toolbar.backing' | head -1 || echo no_toolbar_in_binary

echo "=== layout toolbar state ==="
python3 layout/ft_layout.py toolbar state 2>&1 | head -8

echo "=== control socket ==="
python3 - <<'PY'
import socket
s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
s.bind(b"\0ft_tb2")
s.settimeout(2)
for cmd in (b"state", b"toolbar state"):
    try:
        s.sendto(cmd, b"\0ft_screens")
        print(cmd.decode(), "->", s.recv(4096).decode(errors="replace"))
    except Exception as e:
        print(cmd.decode(), "fail", e)
PY
EOF
