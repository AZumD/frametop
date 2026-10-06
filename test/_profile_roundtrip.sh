#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
. "$root/scripts/_env.sh"

wait_profile() {
  local name=$1 count=$2
  local i
  for i in $(seq 1 45); do
    if ssh -o BatchMode=yes "$FRAME_HOST" bash -s -- "$name" "$count" <<'EOF'
name=$1; count=$2
pid=$(pgrep -x ft-screens | head -1)
[ -n "$pid" ] || exit 1
got=$(tr '\0' '\n' < /proc/$pid/environ | sed -n 's/^FT_SCREEN_COUNT=//p')
[ "$got" = "$count" ] || exit 1
~/dev/frametop/layout/ft-layout profile current | grep -qx "$name"
EOF
    then
      echo "ok $name ($count screens) after $i"
      return 0
    fi
    sleep 2
  done
  echo "FAIL waiting for $name / $count" >&2
  return 1
}

wait_layout_idle() {
  local i
  for i in $(seq 1 90); do
    if ssh -o BatchMode=yes "$FRAME_HOST" \
      '! pgrep -af "[f]t-layout " >/dev/null'; then
      echo "layout idle after $i"
      return 0
    fi
    sleep 1
  done
  echo "layout still busy" >&2
  return 1
}

ssh -o BatchMode=yes "$FRAME_HOST" '~/dev/frametop/layout/ft-layout profile apply Bedmovie --duration 0'
wait_profile Bedmovie 2
wait_layout_idle
ssh -o BatchMode=yes "$FRAME_HOST" '~/dev/frametop/layout/ft-layout profile apply Desktop --duration 0'
wait_profile Desktop 3
echo ROUNDTRIP_OK
