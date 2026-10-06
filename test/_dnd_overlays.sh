#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/Antho/Projects/frametop-customized-main
scripts/frame.sh --host 'bash -s' <<'EOF'
echo "=== float overlays via pointer helper ==="
# ask overlays over abstract socket
python3 - <<'PY'
import socket, os, time
s=socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
s.bind(b'\0ft_dnd_ovl')
s.settimeout(2.0)
s.sendto(b'overlays', b'\0ft_pointer_helper')
try:
    data=s.recv(1<<20)
    text=data.decode('utf-8','replace')
    for line in text.split('\n'):
        if 'frametop.float' in line or 'frametop.screen' in line or 'frametop.catcher' in line:
            print(line[:200])
    print('bytes', len(data))
except Exception as e:
    print('ERR', e)
PY
echo "=== floatd slots ==="
python3 - <<'PY'
import socket
s=socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
s.bind(b'\0ft_dnd_float')
s.settimeout(1)
s.sendto(b'list', b'\0frametop_float')
try:
    print(s.recv(4096))
except Exception as e:
    print(e)
PY
EOF
