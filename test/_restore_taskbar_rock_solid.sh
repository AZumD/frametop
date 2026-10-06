#!/usr/bin/env bash
# Rebuild ft-screens (with toolbar), restart nested desktop, enable toolbar, verify.
# Does not restart SteamVR/gamescope.
set -euo pipefail
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
python3 "$ROOT/test/_fix_crlf_tree.py" >/dev/null 2>&1 || true
bash "$ROOT/scripts/sync.sh"

echo "===== REBUILD ====="
ssh -o BatchMode=yes -o ServerAliveInterval=30 "$FRAME_HOST" bash -s <<'EOF'
set -euo pipefail
export XDG_RUNTIME_DIR=/run/user/$(id -u)
cd /home/steamos/dev/frametop
bash desktops.sh stop || true
pkill -x ft-screens 2>/dev/null || true
pkill -f '^ft-taskbar ' 2>/dev/null || true
rm -f "$XDG_RUNTIME_DIR"/ft-screens-0 "$XDG_RUNTIME_DIR"/ft-screens-0.lock
rm -rf "$XDG_RUNTIME_DIR/frametop" 2>/dev/null || true
bash scripts/rebuild-screens-on-frame.sh
grep -aq -- 'frametop.toolbar' screens/build/ft-screens
grep -aq -- '--spares' screens/build/ft-screens
echo REBUILD_OK
EOF

echo "===== START + ENABLE TOOLBAR ====="
ssh -o BatchMode=yes -o ServerAliveInterval=30 "$FRAME_HOST" bash -s <<'EOF'
set -euo pipefail
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export DBUS_SESSION_BUS_ADDRESS=unix:path=$XDG_RUNTIME_DIR/bus
repo=/home/steamos/dev/frametop
cd "$repo"

bash scripts/start-desktop-on-frame.sh
sleep 6

# Force-enable toolbar in layout + push to ft-screens (rock-solid).
python3 layout/ft_layout.py toolbar enable 2>&1 | tee /tmp/frametop-toolbar-enable.log || true
sleep 2

echo "=== procs ==="
pgrep -af '^ft-taskbar ' | head -2 || echo MISSING_ft-taskbar
pgrep -ax ft-screens | head -1 || echo MISSING_ft-screens
echo "plasmashell=$(pgrep -c plasmashell 2>/dev/null || echo 0)"

echo "=== toolbar state ==="
python3 - <<'PY'
import socket
s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
s.bind(b"\0ft_tb_verify")
s.settimeout(3)
for cmd in (b"toolbar state", b"state"):
    try:
        s.sendto(cmd, b"\0ft_screens")
        print(cmd.decode(), "->", s.recv(8192).decode(errors="replace"))
    except Exception as e:
        print(cmd.decode(), "fail", e)
PY

python3 layout/ft_layout.py toolbar state 2>&1 | head -10 || true
tail -15 /tmp/frametop-taskbar.log 2>/dev/null || echo no_taskbar_log

# Fail hard if toolbar unknown or taskbar missing.
python3 - <<'PY'
import socket, subprocess, sys
s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
s.bind(b"\0ft_tb_gate")
s.settimeout(3)
s.sendto(b"toolbar state", b"\0ft_screens")
reply = s.recv(8192).decode(errors="replace")
print("gate:", reply)
ok = reply.startswith("ok ")
tb = subprocess.call(["pgrep", "-f", "^ft-taskbar "]) == 0
if not ok or not tb:
    print("TASKBAR_NOT_ROCK_SOLID ok=", ok, "ft-taskbar=", tb)
    sys.exit(1)
print("TASKBAR_ROCK_SOLID")
PY
EOF
