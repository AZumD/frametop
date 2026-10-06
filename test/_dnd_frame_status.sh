#!/usr/bin/env bash
# Run on the Frame via: scripts/frame.sh --host 'bash -s' < test/_dnd_frame_status.sh
set -euo pipefail
echo "=== host ==="
hostname
whoami
echo "=== processes ==="
pgrep -a ft-screens || true
pgrep -a ft-pointer || true
echo "=== binaries ==="
ls -la "$HOME/dev/frametop/screens/build/ft-screens" 2>&1 || true
ls -la "$HOME/dev/frametop/pointer/helper/build/ft-pointer" 2>&1 || true
echo "=== exe links ==="
for p in ft-screens ft-pointer; do
  pid=$(pgrep -n "$p" || true)
  if [ -n "${pid:-}" ]; then
    echo "$p pid=$pid -> $(readlink /proc/$pid/exe 2>/dev/null || echo '?')"
  fi
done
echo "=== screens log dnd ==="
grep -E 'dnd |SteamVR game|cant create|can.t create' /tmp/frametop-screens.log 2>/dev/null | tail -40 || true
echo "=== state ==="
python3 -c '
import socket
s=socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
s.bind(b"\0ft_dnd_st")
s.settimeout(2)
try:
    s.sendto(b"state", b"\0ft_screens")
    print(s.recv(4096).decode())
except Exception as e:
    print("state err", e)
'
