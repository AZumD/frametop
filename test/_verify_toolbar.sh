#!/usr/bin/env bash
set -u
ROOT=/mnt/c/Users/Antho/Projects/frametop-stage1-chrome
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
set +e
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export DBUS_SESSION_BUS_ADDRESS=unix:path=$XDG_RUNTIME_DIR/bus
cd /home/steamos/dev/frametop
echo "toolbar string count:" $(strings screens/build/ft-screens | grep -c 'toolbar state')
pgrep -af ft-taskbar | head -2
python3 - <<'PY'
import socket
s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
s.bind(b"\0ft_vtb")
s.settimeout(2)
for c in (b"toolbar state", b"toolbar taskbar"):
    try:
        s.sendto(c, b"\0ft_screens")
        print(c.decode(), "->", s.recv(4096).decode(errors="replace"))
    except Exception as e:
        print(c.decode(), "FAIL", e)
PY
EOF
