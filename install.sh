#!/usr/bin/env bash
# Install everything on the Steam Frame: the build container, Frametop (multi-screen
# desktop, input relay, settings apps), and optionally the Bluetooth fixes and the
# 3D-mouse SteamVR driver. Run it on the headset in a terminal, from this repo. It's
# safe to re-run, for example after `git pull`. (Hand tracking, hands/, is deferred: it
# isn't offered here — install with hands/run.sh install, then ft-handsctl on.)
# (It also works from a PC over SSH; see "Developing from a PC" in the README.)
#
# Usage: ./install.sh [--yes] [--no-bluetooth] [--with-pointer] [--no-pointer]
#   --yes           don't ask; skips Bluetooth and SteamVR restart; pointer stays off
#                   unless --with-pointer is also given
#   --no-bluetooth  don't offer the Bluetooth fixes
#   --with-pointer  register ft_pointer and enable frametop-pointer.service (opt-in)
#   --no-pointer    skip the 3D mouse (default)
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
. "$root/scripts/_env.sh"

assume_yes=0 bluetooth=1 pointer=ask
for arg in "$@"; do
  case $arg in
    --yes) assume_yes=1 ;;
    --no-bluetooth) bluetooth=0 ;;
    --with-pointer) pointer=1 ;;
    --no-pointer) pointer=0 ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done
# --yes without an explicit pointer flag keeps the safe default (no external driver).
[ "$assume_yes" = 1 ] && [ "$pointer" = ask ] && pointer=0

# Only the questions read from the terminal (or whatever stdin is); the build steps get
# no input, so they can't swallow typed-ahead or piped answers.
exec 3<&0 </dev/null

step() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
ask() {  # ask "question" default(y|n)
  [ "$assume_yes" = 1 ] && [ "$2" = y ] && return 0
  [ "$assume_yes" = 1 ] && return 1
  local hint answer
  hint=$([ "$2" = y ] && echo "Y/n" || echo "y/N")
  read -r -p "$1 [$hint] " answer <&3 || answer=
  answer=${answer:-$2}
  [[ $answer =~ ^[Yy] ]]
}

if [ "$FRAME_LOCAL" = 1 ]; then
  echo "Installing on this Steam Frame from $FRAME_REPO"
else
  echo "Installing on $FRAME_HOST over SSH (repo copy at $FRAME_REPO)"
  "$root/scripts/sync.sh" >/dev/null
fi

step "1/7 distrobox (container tool, installed in your home folder)"
if on_frame 'test -x ~/.local/bin/distrobox'; then
  echo "already installed: $(on_frame '~/.local/bin/distrobox version | head -1')"
else
  on_frame 'set -e; mkdir -p ~/dev/src
# A tested release, so upstream changes cannot break new installs.
[ -d ~/dev/src/distrobox ] || git clone --depth 1 --branch 1.8.2.5 https://github.com/89luca89/distrobox.git ~/dev/src/distrobox
cd ~/dev/src/distrobox && ./install --prefix ~/.local'
fi

step "2/7 build container (Fedora 44 'dev', about 1-2 GB the first time)"
"$root/setup/dev-container.sh"

step "3/7 input relay (keeps Bluetooth mice working in SteamVR, device roles, button maps)"
"$root/desktops.sh" relay install
echo "Note: frametop-input-relay.service starts before SteamVR with a 20s READY timeout."
echo "It is WantedBy=steamvr.service only (not default.target). A relay failure must not"
echo "block stock SteamVR. Recover with: scripts/recover-vr.sh"

step "4/7 3D mouse: SteamVR driver + helper (OPTIONAL; can break headset boot if broken)"
if [ "$pointer" = ask ]; then
  if ask "Install the optional 3D-mouse OpenVR driver (ft_pointer)? Prefer No unless you need it." n; then
    pointer=1
  else
    pointer=0
  fi
fi
if [ "$pointer" = 1 ]; then
  "$root/pointer/driver/build.sh"
  "$root/pointer/driver/install.sh" install 2>&1 | grep -v xdg-open
  "$root/pointer/helper/build.sh"
  "$root/pointer/helper/run.sh" install
  on_frame "sed -i 's/^POINTER=0/POINTER=1/' ~/.config/frametop.conf; grep -q '^POINTER=' ~/.config/frametop.conf || echo 'POINTER=1' >> ~/.config/frametop.conf"
  echo "ENABLED (opt-in): ft_pointer registered; frametop-pointer.service enabled; POINTER=1"
  echo "If SteamVR black-screens after restart: $FRAME_REPO/scripts/recover-vr.sh --yes"
else
  echo "skipped (safe default). Enable later with:"
  echo "  pointer/driver/build.sh && pointer/driver/install.sh install"
  echo "  pointer/helper/build.sh && pointer/helper/run.sh install"
  echo "  then set POINTER=1 in ~/.config/frametop.conf and restart SteamVR"
  on_frame "if [ -f ~/.config/frametop.conf ]; then
    sed -i 's/^POINTER=1/POINTER=0/' ~/.config/frametop.conf
    grep -q '^POINTER=' ~/.config/frametop.conf || echo 'POINTER=0' >> ~/.config/frametop.conf
  fi" || true
fi

step "5/7 multi-screen desktop (ft-screens), Frametop Input Settings, and Frametop Display Settings"
"$root/screens/build.sh"
"$root/desktops.sh" install >/dev/null
"$root/input-settings/install.sh"
"$root/display-settings/install.sh"
echo "the launcher's Desktop entry now opens the multi-screen desktop"

step "6/7 Bluetooth fixes (optional; they let LE mice and keyboards like the Swiftpoint Z3 reconnect)"
if [ "$bluetooth" = 1 ] && ask "Install the Bluetooth fixes? They need your password (sudo)." n; then
  "$root/setup/bluetooth/install.sh" install
else
  echo "skipped. Install later with: setup/bluetooth/install.sh install"
fi

step "7/7 Done — what is enabled"
cat <<EOF
Core (always installed by this run):
  - Frametop desktop launcher + ft-screens
  - frametop-input-relay.service (WantedBy=steamvr.service, TimeoutStartSec=20)
  - Frametop Display Settings / Input Settings

Optional VR integration:
  - ft_pointer OpenVR driver: $([ "$pointer" = 1 ] && echo ENABLED || echo disabled)
  - frametop-pointer.service: $([ "$pointer" = 1 ] && echo ENABLED || echo disabled)
  - POINTER in ~/.config/frametop.conf: $([ "$pointer" = 1 ] && echo 1 || echo 0)

Disable / recover over SSH if SteamVR black-screens:
  $FRAME_REPO/scripts/recover-vr.sh --yes
EOF

if [ "$pointer" = 1 ]; then
  cat <<'EOF'

SteamVR has to restart once to load the 3D mouse driver and to start the input relay
before it. Restarting SteamVR closes everything open in VR, including this terminal if
it's in a VR desktop. Rebooting the headset works too.
EOF
else
  cat <<'EOF'

SteamVR restart is only needed if the input relay was newly enabled and you want it
before the next SteamVR start. It is not required for the multi-screen desktop alone.
EOF
fi
cat <<'EOF'

Recommended: stop Steam from putting the headset to sleep while it's plugged in. In Steam,
open Settings > Power, and under "When Plugged In and Idle" set "Sleep after" to Never.
The displays still turn off when you take the headset off.
EOF
if ask "Restart SteamVR now?" n; then
  on_frame 'systemctl --user restart steamvr.service'
fi
