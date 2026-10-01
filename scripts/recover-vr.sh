#!/usr/bin/env bash
# Recover a working SteamVR / headset boot after Frametop optional VR pieces misbehave.
# Safe to run over SSH. Does not reboot, does not restart SteamVR, and does not delete
# layout profiles or other user data under ~/.config/frametop*.
#
# Usage: ./scripts/recover-vr.sh [--yes]
#   --yes  don't ask; perform every recovery step
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
. "$root/scripts/_env.sh"

assume_yes=0
for arg in "$@"; do
  case $arg in
    --yes) assume_yes=1 ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

ask() {
  [ "$assume_yes" = 1 ] && return 0
  local answer
  read -r -p "$1 [y/N] " answer || answer=
  [[ ${answer:-n} =~ ^[Yy] ]]
}

echo "Frametop VR recovery"
if [ "$FRAME_LOCAL" = 1 ]; then
  echo "Running on this Steam Frame from $FRAME_REPO"
else
  echo "Running on $FRAME_HOST over SSH (repo at $FRAME_REPO)"
fi
echo
echo "This will:"
echo "  - stop and disable frametop-pointer.service"
echo "  - stop the input relay and clean its fd store, then leave it enabled for the next SteamVR start"
echo "  - unregister ft_pointer with vrpathreg (after backing up openvrpaths.vrpath)"
echo "  - set POINTER=0 in ~/.config/frametop.conf"
echo "It leaves layout JSON, profiles, desktop launcher settings, and the core input relay installed."
echo

if ! ask "Continue?"; then
  echo "aborted"
  exit 0
fi

dest=/home/steamos/.local/share/frametop/ft_pointer
reg=/opt/steamvr/bin/linuxarm64/vrpathreg
paths='~/.config/openvr/openvrpaths.vrpath'

on_frame "set -e
export XDG_RUNTIME_DIR=/run/user/\$(id -u)
export DBUS_SESSION_BUS_ADDRESS=unix:path=\$XDG_RUNTIME_DIR/bus
CHANGED=0
say() { printf 'CHANGED: %s\n' \"\$*\"; CHANGED=1; }

echo '== systemd services'
unit=frametop-pointer.service
if systemctl --user cat \$unit >/dev/null 2>&1; then
  was_enabled=\$(systemctl --user is-enabled \$unit 2>/dev/null || true)
  was_active=\$(systemctl --user is-active \$unit 2>/dev/null || true)
  systemctl --user disable --now \$unit 2>/dev/null || true
  say \"\$unit: stop/disable (was enabled=\$was_enabled active=\$was_active)\"
else
  echo \"\$unit: not installed (ok)\"
fi

unit=frametop-input-relay.service
if systemctl --user cat \$unit >/dev/null 2>&1; then
  was_enabled=\$(systemctl --user is-enabled \$unit 2>/dev/null || true)
  was_active=\$(systemctl --user is-active \$unit 2>/dev/null || true)
  systemctl --user stop \$unit 2>/dev/null || true
  if systemctl --user clean --what=fdstore \$unit 2>/dev/null; then
    say 'frametop-input-relay: stopped and cleaned fd store'
  else
    say \"frametop-input-relay: stopped (was enabled=\$was_enabled active=\$was_active)\"
  fi
  # The relay is core keyboard/mouse plumbing. Keep it disabled for this running
  # SteamVR recovery, but make sure the next SteamVR start pulls it in again.
  systemctl --user enable \$unit >/dev/null 2>&1 || true
  echo 'frametop-input-relay: enabled for next SteamVR start (not started now)'
else
  echo \"\$unit: not installed (ok)\"
fi

systemctl --user daemon-reload 2>/dev/null || true
if pkill -x ft-pointer 2>/dev/null; then
  say 'killed leftover ft-pointer process'
fi

echo '== OpenVR external driver ft_pointer'
if [ -x $reg ]; then
  show=\$(LD_LIBRARY_PATH=/opt/steamvr/bin/linuxarm64 $reg show 2>/dev/null || true)
  if printf '%s\n' \"\$show\" | grep -F '$dest' >/dev/null; then
    paths_file=\$HOME/.config/openvr/openvrpaths.vrpath
    if [ -f \"\$paths_file\" ]; then
      bak=\$paths_file.frametop-recover.\$(date +%Y%m%d%H%M%S)
      cp -a \"\$paths_file\" \"\$bak\"
      say \"backed up openvrpaths.vrpath -> \$bak\"
    fi
    LD_LIBRARY_PATH=/opt/steamvr/bin/linuxarm64 $reg removedriver $dest
    say \"vrpathreg removedriver $dest\"
  else
    echo 'ft_pointer not registered in vrpathreg (ok)'
  fi
else
  echo 'vrpathreg missing; skipped unregister'
fi
if [ -d $dest ]; then
  echo \"driver files kept at $dest (unregister only; delete manually if you want them gone)\"
fi

echo '== POINTER flag'
conf=\$HOME/.config/frametop.conf
if [ -f \"\$conf\" ] && grep -q '^POINTER=1' \"\$conf\"; then
  sed -i 's/^POINTER=1/POINTER=0/' \"\$conf\"
  say 'set POINTER=0 in ~/.config/frametop.conf'
else
  echo 'POINTER already off or conf missing (ok)'
fi

echo
if [ \$CHANGED -eq 0 ]; then
  echo 'Nothing needed changing.'
else
  echo 'Summary of changes above (lines starting with CHANGED:).'
fi
echo 'Next: reboot the headset, or restart SteamVR yourself, to confirm stock VR boots.'
echo 'The input relay is enabled and will start with SteamVR; the optional 3D pointer stays disabled.'
echo 'Re-enable the optional 3D mouse later with:'
echo '  pointer/driver/install.sh install && pointer/helper/run.sh install'
"