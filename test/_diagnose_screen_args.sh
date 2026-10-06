#!/usr/bin/env bash
set -u
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
set +e
export XDG_RUNTIME_DIR=/run/user/$(id -u)
cd /home/steamos/dev/frametop
echo "=== ft-layout screen-args ==="
python3 layout/ft_layout.py screen-args 2>&1; echo exit=$?
./layout/ft-layout screen-args 2>&1; echo exit2=$?
echo
echo "=== layout file ==="
ls -la ~/.config/frametop-layout.json ~/.config/frametop.conf 2>/dev/null
python3 - <<'PY'
import json
from pathlib import Path
p=Path.home()/'.config'/'frametop-layout.json'
print(p, 'exists', p.is_file())
if p.is_file():
  d=json.loads(p.read_text())
  print('keys', sorted(d.keys())[:30])
  print('screens', d.get('screens') or d.get('displays') or 'missing')
  print('primary', d.get('primary'))
PY
echo
echo "=== layout log ==="
cat /tmp/frametop-layout.log 2>/dev/null | tail -40
echo
echo "=== fg session with traced screen_args ==="
# simulate the critical lines
here=/home/steamos/dev/frametop/session
args=$("$here/../layout/ft-layout" screen-args 2>/tmp/screen-args.err)
echo "raw=[$args]"
echo "stderr:"; cat /tmp/screen-args.err
read -ra screen_args <<< "$args"
echo "count=${#screen_args[@]}"
printf 'arg=%q\n' "${screen_args[@]}"
EOF
