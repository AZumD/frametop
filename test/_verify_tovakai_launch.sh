#!/usr/bin/env bash
# After a Tovakai pick: check wrapper log, nested display, Hades / Proton, desktop mode signals.
set -u
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
set +e
export XDG_RUNTIME_DIR=/run/user/$(id -u)
echo "=== ft-game-run / launch options ==="
tail -40 /tmp/frametop-game-run.log 2>/dev/null || echo no_game_run_log
ls -la /tmp/frametop-game-run* 2>/dev/null
echo
echo "=== plasmashell.env display ==="
envf="$XDG_RUNTIME_DIR/frametop/plasmashell.env"
if [ -f "$envf" ]; then
  tr '\0' '\n' < "$envf" | grep -E '^(DISPLAY|WAYLAND_DISPLAY|XAUTHORITY|XDG_RUNTIME_DIR)=' || true
else
  echo missing_plasmashell_env
fi
echo
echo "=== procs ==="
pgrep -af 'Hades|hades|proton|ft-game-run|reaper' 2>/dev/null | grep -v pgrep | head -20
echo "ft-screens=$(pgrep -c -x ft-screens 2>/dev/null || echo 0)"
echo "plasmashell=$(pgrep -c plasmashell 2>/dev/null || echo 0)"
echo
echo "=== X displays / wayland ==="
ls -la /tmp/.X11-unix 2>/dev/null | head -10
ls -la "$XDG_RUNTIME_DIR"/wayland-* 2>/dev/null | head -10
ls -la "$XDG_RUNTIME_DIR"/frametop/wayland-* 2>/dev/null | head -10
echo
echo "=== Steam launch options for 1145360 (best effort) ==="
# leave for CDP; just note wrapper presence on disk
test -x /home/steamos/dev/frametop/session/ft-game-run && echo ft-game-run=executable || echo ft-game-run=MISSING
EOF
