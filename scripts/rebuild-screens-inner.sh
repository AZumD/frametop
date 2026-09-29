#!/usr/bin/env bash
# Run inside the Frame's "dev" distrobox, cwd = screens/.
set -euo pipefail
mkdir -p build/include
openvr=v2.15.6
if [ ! -f "build/include/openvr-$openvr" ]; then
  curl -fsSL "https://raw.githubusercontent.com/ValveSoftware/openvr/$openvr/headers/openvr.h" -o build/include/openvr.h
  touch "build/include/openvr-$openvr"
fi
gcc -std=c11 -O2 -Wall -Wno-unused-parameter -c -o build/compositor.o compositor.c \
  $(pkg-config --cflags wlroots-0.20 wayland-server xkbcommon libdrm pixman-1)
g++ -std=c++17 -O2 -Wall -Wno-missing-field-initializers -Ibuild/include -c -o build/vr.o vr.cpp
g++ -o build/ft-screens build/compositor.o build/vr.o \
  $(pkg-config --libs wlroots-0.20 wayland-server xkbcommon) \
  -L/opt/steamvr/bin/linuxarm64 -lopenvr_api -Wl,-rpath,/opt/steamvr/bin/linuxarm64
cp -f actions.json bindings_frame_hmd.json bindings_hmd.json build/
echo BUILT
ls -la build/ft-screens build/*.json
strings build/ft-screens | grep -E 'err=%d flags|eye tracking: action' | head
