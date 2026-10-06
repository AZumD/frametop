#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/Antho/Projects/frametop-customized-main
scripts/frame.sh --host 'bash -s' <<'EOF'
echo "=== float surface/scale lines ==="
grep -E 'screen [4-9]:|floating|surface|output scale|spare' /tmp/frametop-screens.log | tail -60
echo "=== ask scales / screens ==="
# try control socket
python3 - <<'PY'
import socket
s=socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
s.bind(b'\0ft_dnd_probe')
s.settimeout(1)
for cmd in [b'screens', b'concealed']:
    try:
        s.sendto(cmd, b'\0ft_screens')
        print(cmd, s.recv(4096))
    except Exception as e:
        print(cmd, e)
PY
EOF
