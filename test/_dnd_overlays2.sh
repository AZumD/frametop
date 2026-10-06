#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/Antho/Projects/frametop-customized-main
scripts/frame.sh --host 'bash -s' <<'EOF'
python3 - <<'PY'
import socket, json
s=socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
s.bind(b'\0ft_dnd_ovl2')
s.settimeout(3.0)
s.sendto(b'overlays', b'\0ft_pointer_helper')
data=s.recv(1<<20)
text=data.decode()
print('raw prefix', text[:120])
# try parse
try:
    # may be JSON object or datagram with framing
    j=json.loads(text)
except Exception as e:
    print('json err', e)
    # find frametop occurrences
    print('frametop count', text.count('frametop'))
    idx=0
    n=0
    while n<30:
        i=text.find('frametop', idx)
        if i<0: break
        print(text[i:i+80])
        idx=i+1; n+=1
    raise SystemExit
print('keys sample:')
lst=j.get('list') or j
if isinstance(lst, dict):
    lst=lst.get('list', [])
frametop=[e for e in lst if str(e.get('key','')).startswith('frametop.')]
print('frametop overlays', len(frametop))
for e in frametop:
    print(e.get('key'), 'vis', e.get('visible'))
print('total', len(lst))
PY
EOF
