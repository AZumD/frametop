#!/usr/bin/env bash
# Live, non-destructive probe of SteamVR's public IVROverlay native keyboard.
#
# Works from the PC or directly on the Frame. It does NOT restart Frametop/SteamVR.
# SteamVR must already be running.
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
. "$root/scripts/_env.sh"

if ! on_frame 'pgrep -x vrserver >/dev/null'; then
    echo "SteamVR is not running; refusing to start an OpenVR overlay probe." >&2
    exit 1
fi

"$root/scripts/sync.sh" >/dev/null

echo "=== building native keyboard probe in dev container ==="
"$root/scripts/frame.sh" -C test 'set -e
mkdir -p build ../screens/build/include
openvr=v2.15.6
if [ ! -f "../screens/build/include/openvr-$openvr" ]; then
  curl -fsSL "https://raw.githubusercontent.com/ValveSoftware/openvr/$openvr/headers/openvr.h" \
    -o ../screens/build/include/openvr.h
  touch "../screens/build/include/openvr-$openvr"
fi
g++ -std=c++17 -O2 -Wall -Wextra -I../screens/build/include \
  native_keyboard_probe.cpp -o build/ft-kbprobe \
  -L/opt/steamvr/bin/linuxarm64 -lopenvr_api \
  -Wl,-rpath,/opt/steamvr/bin/linuxarm64
echo "built test/build/ft-kbprobe"'

echo
echo "=== requesting SteamVR native keyboard ==="
echo "Close the keyboard when finished; Ctrl-C also cleans it up."
echo
exec "$root/scripts/frame.sh" -C test 'build/ft-kbprobe 90'
