#!/usr/bin/env bash
# Build ft-screens in the dev container on the Frame (screens/build/ft-screens).
# compositor.c is the wlroots side (C; wlroots headers aren't C++), vr.cpp the OpenVR side.
# vr.cpp needs OpenVR's IVRIPCResourceManagerClient (ImportDmabuf), which the header
# shipped with SteamVR on the Frame predates, so the build uses the public header from
# Valve's openvr repo (pinned; the Frame's runtime supports its interface versions).
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
"$root/scripts/sync.sh" >/dev/null
exec "$root/scripts/frame.sh" -C screens 'set -e; mkdir -p build/include
openvr=v2.15.6
[ -f build/include/openvr-$openvr ] || { curl -fsSL "https://raw.githubusercontent.com/ValveSoftware/openvr/$openvr/headers/openvr.h" -o build/include/openvr.h && touch build/include/openvr-$openvr; }
gcc -std=c11 -O2 -Wall -Wno-unused-parameter -c -o build/compositor.o compositor.c \
  $(pkg-config --cflags wlroots-0.20 wayland-server xkbcommon libdrm pixman-1)
# stb_image: PNG/JPEG/GIF (+ animated GIF) for the Image spatial instrument (pinned).
stb=fede005abaf93d9d7f3a679d1999b2db341b360f
[ -f build/include/stb_image-$stb ] || {
  curl -fsSL "https://raw.githubusercontent.com/nothings/stb/$stb/stb_image.h" -o build/include/stb_image.h
  touch "build/include/stb_image-$stb"
}
# stb_truetype: key labels on Frametop'\''s VR keyboard (keyboard.cpp).
stbt=2c980bb59875b0d32144a71867fbdebb2f77cd20
[ -f build/include/stb_truetype-$stbt ] || {
  curl -fsSL "https://raw.githubusercontent.com/nothings/stb/$stbt/stb_truetype.h" -o build/include/stb_truetype.h
  touch "build/include/stb_truetype-$stbt"
}
cxx="g++ -std=c++17 -O2 -Wall -Wno-missing-field-initializers -Wno-unused-parameter -Ibuild/include $(pkg-config --cflags egl glesv2 gbm libdrm)"
$cxx -c -o build/vr.o vr.cpp
$cxx -c -o build/keyboard.o keyboard.cpp
$cxx -c -o build/handcut.o handcut.cpp
$cxx -c -o build/handtest.o handtest.cpp
vrlibs="$(pkg-config --libs egl glesv2 gbm) -L/opt/steamvr/bin/linuxarm64 -lopenvr_api -Wl,-rpath,/opt/steamvr/bin/linuxarm64"
g++ -o build/ft-screens build/compositor.o build/vr.o build/keyboard.o build/handcut.o \
  $(pkg-config --libs wlroots-0.20 wayland-server xkbcommon) $vrlibs
g++ -o build/ft-handtest build/handtest.o build/handcut.o $vrlibs
cp -f actions.json build/actions.json
cp -f bindings_frame_hmd.json bindings_hmd.json build/
echo "built build/ft-screens build/ft-handtest"'
