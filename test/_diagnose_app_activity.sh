#!/usr/bin/env bash
# Diagnose stuck AppActivity / hidden Frametop desktop on the Frame.
set -u
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
set +e
echo "=== processes ==="
pgrep -ax ft-screens | head -5
pgrep -ax gamescope | head -3
echo "=== app_activity log ==="
grep app_activity /tmp/frametop-screens.log 2>/dev/null | tail -30
echo "=== other log tail ==="
tail -30 /tmp/frametop-screens.log 2>/dev/null
echo "=== ft-screens state ==="
python3 - <<'PY'
import socket
s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
s.bind(b"\0ft_act_chk")
s.settimeout(2)
for cmd in (b"state",):
    try:
        s.sendto(cmd, b"\0ft_screens")
        print(cmd.decode(), "->", s.recv(4096).decode(errors="replace"))
    except Exception as e:
        print(cmd.decode(), "fail", e)
PY
echo "=== overlays ==="
python3 - <<'PY'
import socket, json
s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
s.bind(b"\0ft_act_ovl")
s.settimeout(2)
try:
    s.sendto(b"overlays", b"\0ft_pointer_helper")
    lst = json.loads(s.recv(1 << 20).decode())["list"]
except Exception as e:
    print("overlay fail", e)
    raise SystemExit
for e in lst:
    k = e.get("key", "")
    if "desktopgame" in k or "gamescope" in k.lower() or (
        e.get("visible") and not k.startswith("frametop.")
    ):
        print(("VIS" if e.get("visible") else "hid"), k, e.get("name", ""))
ft = [e for e in lst if e["key"].startswith("frametop.")]
print("frametop total", len(ft), "visible", sum(1 for e in ft if e.get("visible")))
for e in ft:
    if e.get("visible"):
        print(" ", e["key"])
PY
EOF
