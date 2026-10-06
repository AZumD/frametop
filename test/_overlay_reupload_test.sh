#!/usr/bin/env bash
# Hypothesis test for the toolbar's invisible hit pane: SteamVR reports texture size 0x0
# for toolbar overlays whose only SetOverlayRaw happened before they were shown. Re-send
# the current tray volume state (ft-screens redraws the volume button while visible),
# then ask SteamVR (vrprobe) whether that button now reports a texture size. Changes no
# state: the volume values sent are the ones ft-screens already has.
set -uo pipefail
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
set +e
repo=/home/steamos/dev/frametop
probe=$repo/pointer/probe/build/vrprobe
keys="frametop.toolbar.backing frametop.toolbar.m3.c0 frametop.toolbar.m3.c1"
show() { ~/.local/bin/distrobox enter dev -- "$probe" $keys 2>&1 </dev/null | grep '^overlay' | awk '{print $2, $5, $6}'; }
echo "--- before"; show
python3 - <<'PY'
import re, socket
s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM); s.bind(""); s.settimeout(3)
def ask(cmd):
    s.sendto(cmd.encode(), b"\0ft_screens"); r = s.recv(8192).decode(errors="replace"); print(cmd, "->", r); return r
st = ask("toolbar taskbar")
m = re.search(r"volume=(-?\d+)/(-?\d+)", st)
ask(f"toolbar tray volume {m.group(1)} {m.group(2)}" if m else "toolbar tray volume 0 0")
PY
sleep 1
echo "--- after re-upload of m3.c0 (volume)"; show
EOF
