#!/usr/bin/env bash
# Ask the running ft-screens for every visible Frametop overlay that takes laser input
# (key, alpha, width x height in metres, world y). An invisible pane that blocks the
# laser shows up as a row with a low alpha or an unexpected size. Read-only: restarts
# nothing. Needs an ft-screens that has the `toolbar overlays` command.
set -uo pipefail
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
set +e
pgrep -x ft-screens >/dev/null || { echo "ft-screens is not running"; exit 1; }
python3 - <<'PY'
import socket
s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM); s.bind(""); s.settimeout(3)
for cmd in ("toolbar state", "toolbar taskbar", "toolbar overlays"):
    s.sendto(cmd.encode(), b"\0ft_screens")
    print(cmd, "->", s.recv(8192).decode(errors="replace"))
PY
EOF
