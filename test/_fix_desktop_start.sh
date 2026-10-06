#!/usr/bin/env bash
# Rebuild ft-screens in distrobox if needed, then start Frametop desktop.
set -euo pipefail
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
bash "$ROOT/scripts/sync.sh" >/tmp/ft_sync_desktop.txt 2>&1 || true
ssh -o BatchMode=yes "$FRAME_HOST" 'bash -s' <<'EOF'
set -euo pipefail
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export DBUS_SESSION_BUS_ADDRESS=unix:path=$XDG_RUNTIME_DIR/bus
repo=/home/steamos/dev/frametop
cd "$repo"

echo "=== screen-args ==="
python3 layout/ft_layout.py screen-args 2>&1 || ./layout/ft-layout screen-args 2>&1 || true

echo "=== distrobox ==="
~/.local/bin/distrobox list 2>&1 | head -10

echo "=== rebuild screens (distrobox) ==="
bash scripts/rebuild-screens-on-frame.sh 2>&1 | tail -50

echo "=== ft-screens in container ==="
~/.local/bin/distrobox enter dev -- bash -lc 'ldd /home/steamos/dev/frametop/screens/build/ft-screens 2>&1 | grep "not found" || echo ldd_ok; /home/steamos/dev/frametop/screens/build/ft-screens 2>&1 | head -2' || true

echo "=== steamvr ==="
systemctl --user is-active steamvr.service || true
pgrep -x vrserver >/dev/null && echo vrserver=yes || echo vrserver=no
pgrep -x vrcompositor >/dev/null && echo vrcompositor=yes || echo vrcompositor=no

echo "=== start ==="
bash scripts/start-desktop-on-frame.sh 2>&1
sleep 3
echo "=== running ==="
pgrep -ax ft-screens | head -3 || echo 'no ft-screens'
pgrep -c plasmashell || echo 'no plasmashell'
echo "=== screens log ==="
tail -40 /tmp/frametop-screens.log || true
echo "=== session log ==="
tail -30 /tmp/frametop-session.log || true
EOF
