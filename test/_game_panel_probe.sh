#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/Antho/Projects/frametop-customized-main
scripts/frame.sh --host 'bash -s' <<'EOF'
echo "=== overlay count (vrcmd) ==="
python3 - <<'PY'
import socket, json
s=socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
s.bind(b'\0ft_game_ovl')
s.settimeout(3)
s.sendto(b'overlays', b'\0ft_pointer_helper')
data=s.recv(1<<20)
j=json.loads(data.decode())
lst=j['list']
print('total listed', len(lst))
frametop=[e for e in lst if e['key'].startswith('frametop.')]
print('frametop', len(frametop), 'visible', sum(1 for e in frametop if e['visible']))
desk=[e for e in lst if 'desktopgame' in e['key'] or 'games' in e['key'].lower() or 'gamescope' in e['name'].lower()]
print('game-ish:')
for e in desk[:40]:
    print(e['key'], e['name'], 'vis', e['visible'])
print('--- all visible non-frametop ---')
for e in lst:
    if e['visible'] and not e['key'].startswith('frametop.'):
        print(e['key'], e['name'])
PY
echo "=== processes ==="
pgrep -a gamescope | head -10 || true
pgrep -a steam | head -5 || true
echo "=== screens log tail ==="
tail -40 /tmp/frametop-screens.log 2>/dev/null || true
EOF
