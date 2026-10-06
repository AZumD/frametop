#!/usr/bin/env bash
set -u
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
set +e
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export DBUS_SESSION_BUS_ADDRESS=unix:path=$XDG_RUNTIME_DIR/bus
repo=/home/steamos/dev/frametop
cd "$repo"

echo "=== unit ==="
systemctl --user status frametop-desktop.service --no-pager -l 2>&1 | head -40
journalctl --user -u frametop-desktop.service -n 50 --no-pager 2>&1 | tail -50

echo
echo "=== logs sizes ==="
wc -c /tmp/frametop-session.log /tmp/frametop-screens.log 2>/dev/null
echo "---- session ----"; cat /tmp/frametop-session.log 2>/dev/null | tail -60
echo "---- screens ----"; cat /tmp/frametop-screens.log 2>/dev/null | tail -40

echo
echo "=== distrobox ft-screens dry-run ==="
$HOME/.local/bin/distrobox enter dev -- /home/steamos/dev/frametop/screens/build/ft-screens --help 2>&1 | head -5
$HOME/.local/bin/distrobox enter dev -- ldd /home/steamos/dev/frametop/screens/build/ft-screens 2>&1 | grep 'not found' | head || echo 'ldd ok in distrobox'

echo
echo "=== manual session start (foreground 8s) ==="
# Don't leave it running if it hangs — timeout
timeout 8 bash -x session/frametop-session.sh > /tmp/frametop-session-fg.log 2>&1
ec=$?
echo fg_exit=$ec
tail -80 /tmp/frametop-session-fg.log
echo "---- screens after fg ----"
tail -30 /tmp/frametop-screens.log
EOF
