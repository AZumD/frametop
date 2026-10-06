#!/usr/bin/env bash
# Build and run test/overlay_aspect_probe.cpp in the dev container on the Frame: checks
# whether SteamVR hit-tests SetOverlayRaw overlays by texture aspect or as squares, with
# and without SetOverlayMouseScale. Its overlays are alpha 0, 3 m under the floor, and
# destroyed at once; nothing else is touched.
set -uo pipefail
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
bash "$ROOT/scripts/sync.sh" >/dev/null
bash "$ROOT/scripts/frame.sh" -C test 'set -e; mkdir -p ../build
g++ -std=c++17 -O2 -Wall -I/opt/steamvr/tools/hellovr_vulkan_linux/src/openvr/headers \
  -o ../build/overlay_aspect_probe overlay_aspect_probe.cpp -L/opt/steamvr/bin/linuxarm64 -lopenvr_api \
  -Wl,-rpath,/opt/steamvr/bin/linuxarm64
../build/overlay_aspect_probe </dev/null'
