#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
. "$root/scripts/_env.sh"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
pid=$(pgrep -x ft-screens | head -1)
echo "pid=$pid"
if [ -n "$pid" ]; then
  ls -l /proc/$pid/exe
  stat -c 'bin_mtime=%y' /home/steamos/dev/frametop/screens/build/ft-screens
  ps -o lstart= -p $pid
fi
python3 - <<'PY'
import socket
s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
s.bind("")
s.settimeout(2)
for cmd in ("state", "cutouts state", "controllers always"):
    try:
        s.sendto(cmd.encode(), "\0ft_screens")
        print(repr(cmd), "->", s.recv(512).decode(errors="replace").strip())
    except Exception as e:
        print(repr(cmd), "ERR", e)
PY
EOF

echo "== PC ctl =="
"$root/hands/ft-handsctl" status
"$root/hands/ft-handsctl" cutouts state || true
