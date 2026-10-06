#!/usr/bin/env bash
# Quick post-SteamVR-restart desktop health check (read-only).
set -u
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
set +e
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export DBUS_SESSION_BUS_ADDRESS=unix:path=$XDG_RUNTIME_DIR/bus
repo=/home/steamos/dev/frametop

echo "=== SteamVR / compositor ==="
systemctl --user is-active steamvr.service 2>/dev/null
pgrep -x vrserver >/dev/null && echo vrserver=yes || echo vrserver=no
pgrep -x vrcompositor >/dev/null && echo vrcompositor=yes || echo vrcompositor=no
pgrep -x gamescope >/dev/null && echo gamescope=yes || echo gamescope=no

echo
echo "=== Frametop desktop units / procs ==="
systemctl --user is-active frametop-desktop.service 2>/dev/null || echo frametop-desktop=absent
systemctl --user status frametop-desktop.service --no-pager -l 2>/dev/null | head -25
pgrep -af 'ft-screens|ft-launch|ft-taskbar|plasmashell|kwin_wayland|frametop-session' 2>/dev/null | grep -v 'pgrep' | head -25

echo
echo "=== sockets / runtime ==="
ls -la "$XDG_RUNTIME_DIR"/ft-screens* 2>/dev/null || echo 'no ft-screens sockets'
ls -la "$XDG_RUNTIME_DIR"/frametop 2>/dev/null | head -20 || echo 'no frametop runtime'
test -f "$XDG_RUNTIME_DIR"/frametop/plasmashell.env && echo plasmashell.env=yes || echo plasmashell.env=no
test -f "$XDG_RUNTIME_DIR"/frametop/session-active && echo session-active=yes || echo session-active=no

echo
echo "=== recent logs ==="
for f in /tmp/frametop-screens.log /tmp/frametop-session.log /tmp/frametop-desktop.log /tmp/frametop-plasmashell-watchdog.log; do
  if [ -f "$f" ]; then
    echo "---- $f (tail) ----"
    tail -30 "$f"
  fi
done
journalctl --user -u frametop-desktop.service -n 40 --no-pager 2>/dev/null | tail -40

echo
echo "=== how start is usually invoked ==="
ls -la ~/.local/bin/frametop* "$repo/scripts/start-desktop-on-frame.sh" "$repo/desktops.sh" 2>/dev/null | head
command -v start-frametop-desktop 2>/dev/null
EOF
