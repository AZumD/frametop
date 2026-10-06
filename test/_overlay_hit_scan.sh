#!/usr/bin/env bash
# Measure the real laser hit area SteamVR uses for Frametop overlays (vrprobe --scan:
# rays from the eye, ComputeOverlayIntersection). Compare with the visual size: a hit
# area much taller than the art is an invisible pane. Read-only.
# Usage: test/_overlay_hit_scan.sh [overlay-key ...]
set -uo pipefail
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
keys="${*:-frametop.toolbar.backing frametop.toolbar.grab frametop.toolbar.m1.plate frametop.toolbar.m3.c0 frametop.screen.1.bar}"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s -- $keys <<'EOF'
set +e
probe=/home/steamos/dev/frametop/pointer/probe/build/vrprobe
for k in "$@"; do
  ~/.local/bin/distrobox enter dev -- "$probe" --scan "$k" 0.25 2>&1 </dev/null | grep -E '^(scan|center|no overlay)'
done
EOF
