#!/usr/bin/env bash
# Read-only: list every Frametop toolbar / screen overlay as SteamVR sees it (visible,
# width, texture size, position, input method, and whether the ft_pointer laser or the
# head ray hits it) using pointer/probe/vrprobe as a background OpenVR client. Finds
# invisible panes that catch the laser. Restarts nothing; builds vrprobe in the dev
# container if it is missing.
set -uo pipefail
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
set +e
repo=/home/steamos/dev/frametop
pgrep -x ft-screens >/dev/null || { echo "ft-screens is not running"; exit 1; }
probe=$(ls "$repo"/pointer/probe/build/vrprobe "$repo"/pointer/build/vrprobe 2>/dev/null | head -1)
if [ -z "$probe" ]; then
  echo "vrprobe not built; files in pointer/probe:"; ls "$repo/pointer/probe"
  exit 2
fi
keys="frametop.toolbar.backing frametop.toolbar.grab frametop.toolbar.popup frametop.toolbar.popup.hl"
for m in 0 1 2 3 4 5 6 7; do
  keys="$keys frametop.toolbar.m$m.plate"
  for c in 0 1 2 3 4 5 6 7 8; do keys="$keys frametop.toolbar.m$m.c$c"; done
done
for n in 1 2 3 4 5 6; do
  keys="$keys frametop.screen.$n"
  for p in bar curve roll resize anchor dock slot1 slot2 slot3 slot4 slot5 slot6; do keys="$keys frametop.screen.$n.$p"; done
done
# shellcheck disable=SC2086
out=$(~/.local/bin/distrobox enter dev -- "$probe" $keys 2>&1 </dev/null)
echo "$out" | grep -E '^overlay frametop|primary dashboard|left hand|ft_pointer origin' || echo "$out" | tail -20
EOF
