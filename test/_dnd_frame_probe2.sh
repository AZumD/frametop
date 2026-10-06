#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/Antho/Projects/frametop-customized-main
scripts/frame.sh --host 'bash -s' <<'EOF'
hostname; whoami
pgrep -a ft-screens || true
pgrep -a ft-pointer || true
ls -la ~/dev/frametop/screens/build/ft-screens ~/dev/frametop/pointer/helper/build/ft-pointer 2>&1 || true
for p in ft-screens ft-pointer; do
  pid=$(pgrep -n "$p" || true)
  [ -n "$pid" ] && echo "$p pid=$pid exe=$(readlink /proc/$pid/exe 2>/dev/null)"
done
grep -E 'dnd |SteamVR game' /tmp/frametop-screens.log 2>/dev/null | tail -20 || true
python3 -c "import socket;s=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM);s.bind(b'\0ft_dnd_st');s.settimeout(2);s.sendto(b'state',b'\0ft_screens');print(s.recv(4096).decode())"
EOF
