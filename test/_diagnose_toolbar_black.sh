#!/usr/bin/env bash
# Capture the live state behind the "black toolbar backing, invisible buttons" bug.
# Safe while wearing the headset: read-only, no Frametop/SteamVR restarts.
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
. "$root/scripts/_env.sh"

if ! on_frame 'pgrep -x vrserver >/dev/null'; then
    echo "SteamVR is not running." >&2
    exit 1
fi

"$root/scripts/sync.sh" >/dev/null

echo "=== ft-screens control state ==="
on_frame_script <<'FRAME'
python3 - <<'PY'
import os, socket
for cmd in (b"state", b"toolbar taskbar", b"toolbar overlays"):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    s.settimeout(2)
    s.bind(f"\0ft_toolbar_diag_{os.getpid()}_{id(s)}")
    try:
        for dest in (b"\0ft_screens-0", b"\0ft_screens"):
            try:
                s.sendto(cmd, dest)
                data = s.recv(65535)
                print(cmd.decode(), "->")
                print(data.decode(errors="replace"))
                break
            except (TimeoutError, socket.timeout):
                continue
        else:
            print(cmd.decode(), "-> no ft-screens reply")
    finally:
        s.close()
PY

echo
echo "=== recent toolbar log ==="
if [ -f /tmp/frametop-screens.log ]; then
    grep -iE 'toolbar|SetOverlayRaw|overlay.*error' /tmp/frametop-screens.log | tail -100 || true
else
    echo "no /tmp/frametop-screens.log"
fi
FRAME

echo
echo "=== OpenVR toolbar overlay autopsy ==="
"$root/scripts/frame.sh" -C test 'set -e
mkdir -p build ../screens/build/include
openvr=v2.15.6
if [ ! -f "../screens/build/include/openvr-$openvr" ]; then
  curl -fsSL "https://raw.githubusercontent.com/ValveSoftware/openvr/$openvr/headers/openvr.h" \
    -o ../screens/build/include/openvr.h
  touch "../screens/build/include/openvr-$openvr"
fi
g++ -std=c++17 -O2 -Wall -Wextra -I../screens/build/include \
  toolbar_black_probe.cpp -o build/ft-tbprobe \
  -L/opt/steamvr/bin/linuxarm64 -lopenvr_api \
  -Wl,-rpath,/opt/steamvr/bin/linuxarm64
build/ft-tbprobe'
