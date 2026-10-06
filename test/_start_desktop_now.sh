#!/usr/bin/env bash
set -u
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
ssh -o BatchMode=yes "$FRAME_HOST" 'bash -s' <<'EOF'
set +e
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export DBUS_SESSION_BUS_ADDRESS=unix:path=$XDG_RUNTIME_DIR/bus
cd /home/steamos/dev/frametop
echo "=== before ==="
pgrep -ax ft-screens | head -3 || echo none
systemctl --user is-active steamvr.service
pgrep -x vrserver >/dev/null && echo vrserver=yes || echo vrserver=no
pgrep -x vrcompositor >/dev/null && echo vrcompositor=yes || echo vrcompositor=no
echo "=== start ==="
bash scripts/start-desktop-on-frame.sh
ec=$?
echo start_exit=$ec
sleep 4
echo "=== after ==="
pgrep -ax ft-screens | head -5 || echo none
pgrep -c plasmashell; pgrep -ax plasmashell | head -3
echo "=== screens log ==="
tail -50 /tmp/frametop-screens.log
echo "=== session log ==="
tail -40 /tmp/frametop-session.log
echo "=== app_activity ==="
grep app_activity /tmp/frametop-screens.log | tail -10
EOF
