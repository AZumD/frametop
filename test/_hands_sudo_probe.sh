#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
. "$root/scripts/_env.sh"
bin=/home/steamos/dev/frametop/hands/build/ft-camd
caps=cap_sys_ptrace,cap_perfmon,cap_dac_read_search+ep

echo "== sudo -n probe =="
ssh -o BatchMode=yes "$FRAME_HOST" "sudo -n true && echo NOPASSWD_OK || echo NEED_PASSWORD"

echo "== try setcap via sudo -n =="
if ssh -o BatchMode=yes "$FRAME_HOST" "sudo -n setcap $caps $bin && getcap $bin"; then
  echo SETCAP_OK
else
  echo SETCAP_NEED_PASSWORD
fi

echo "== desktop service =="
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
systemctl --user list-units --type=service --all 'frametop*' --no-pager
echo ---
ls ~/.config/systemd/user/ 2>/dev/null | grep -i frametop || true
echo ---
systemctl --user is-active frametop-desktop.service 2>&1 || true
# how is ft-screens parented?
pid=$(pgrep -x ft-screens | head -1)
[ -n "$pid" ] && tr '\0' ' ' < /proc/$pid/environ | tr ' ' '\n' | grep -E 'INVOCATION|SYSTEMD|MANAGER' || true
pstree -sp "$pid" 2>/dev/null | head -3 || ps -o ppid=,cmd= -p "$pid"
EOF
