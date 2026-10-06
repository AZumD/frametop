#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
. "$root/scripts/_env.sh"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
echo "pgrep ft-screens:"; pgrep -a ft-screens || echo none
echo "pgrep screens:"; pgrep -af 'ft-screens|screens/build' || true
echo "unit:"; systemctl --user status frametop-screens.service --no-pager -l 2>&1 | head -20 || true
# Ask whoever owns @ft_screens
python3 - <<'PY'
import socket
s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
s.bind("")
s.settimeout(2)
for cmd in ("help", "status", "cutouts state"):
    try:
        s.sendto(cmd.encode(), "\0ft_screens")
        print(cmd, "->", s.recv(512).decode(errors="replace").strip())
    except Exception as e:
        print(cmd, "ERR", e)
PY
EOF
