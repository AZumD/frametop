#!/usr/bin/env bash
# Sync, rebuild ft-screens in the Frame's distrobox, verify linkage, start desktop.
set -euo pipefail
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
bash "$ROOT/scripts/sync.sh"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
set -euo pipefail
export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
export DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}
repo=/home/steamos/dev/frametop
cd "$repo"
echo "=== rebuild in distrobox ==="
bash scripts/frame.sh -C screens 'bash build.sh' 2>&1 | tail -40
echo "=== binary check (inside distrobox) ==="
bash scripts/frame.sh -C screens 'ldd build/ft-screens 2>&1 | grep -E "not found|wlroots|GLIBC" || echo ldd_ok; ./build/ft-screens --help 2>&1 | head -3' || true
echo "=== steamvr health ==="
systemctl --user is-active steamvr.service || true
pgrep -x vrcompositor >/dev/null && echo vrcompositor=yes || echo vrcompositor=no
pgrep -x vrserver >/dev/null && echo vrserver=yes || echo vrserver=no
echo "=== start desktop ==="
bash scripts/start-desktop-on-frame.sh
echo "=== post ==="
pgrep -ax ft-screens | head -3
sleep 2
tail -20 /tmp/frametop-screens.log 2>/dev/null || true
grep app_activity /tmp/frametop-screens.log 2>/dev/null | tail -5 || true
EOF
