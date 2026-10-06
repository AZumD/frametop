#!/usr/bin/env bash
# Why won't Frametop desktop start?
set -u
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
set +e
export XDG_RUNTIME_DIR=/run/user/$(id -u)
echo "=== user units ==="
systemctl --user --no-pager --full status frametop-desktop.service 2>&1 | tail -40
echo "=== recent journal ==="
journalctl --user -u frametop-desktop.service -n 40 --no-pager 2>&1 | tail -40
echo "=== related procs ==="
pgrep -ax 'ft-screens|ft-taskbar|ft-launch|plasmashell|kwin|frametop' 2>/dev/null | head -40
echo "=== desktop launchers ==="
ls -la ~/dev/frametop/desktops.sh ~/Desktop/*[Ff]rame* ~/Desktop/*[Dd]esktop* 2>/dev/null | head
echo "=== last screens / session logs ==="
ls -lt /tmp/frametop*.log 2>/dev/null | head
for f in /tmp/frametop-screens.log /tmp/frametop-session.log /tmp/frametop-desktop.log /tmp/frametop-taskbar.log; do
  [ -f "$f" ] || continue
  echo "---- $f ----"
  tail -50 "$f"
done
echo "=== try start-desktop dry hints ==="
cd /home/steamos/dev/frametop 2>/dev/null || cd ~/dev/frametop
# Did our rebuild leave a broken binary?
ls -la screens/build/ft-screens 2>/dev/null
screens/build/ft-screens --help 2>&1 | head -5
file screens/build/ft-screens 2>/dev/null
ldd screens/build/ft-screens 2>&1 | grep -i 'not found' | head
EOF
