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
echo "  - stop and disable frametop-pointer.service and frametop-input-relay.service"
echo "  - clean the input-relay fd store if present"
echo "  - unregister ft_pointer with vrpathreg (after backing up openvrpaths.vrpath)"
echo "  - set POINTER=0 in ~/.config/frametop.conf"
echo "It leaves layout JSON, profiles, and desktop launcher settings intact."
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
for unit in frametop-pointer.service frametop-input-relay.service; do
  if systemctl --user cat \$unit >/dev/null 2>&1; then
    was_enabled=\$(systemctl --user is-enabled \$unit 2>/dev/null || true)
    was_active=\$(systemctl --user is-active \$unit 2>/dev/null || true)
    systemctl --user disable --now \$unit 2>/dev/null || true
    say \"\$unit: stop/disable (was enabled=\$was_enabled active=\$was_active)\"
  else
    echo \"\$unit: not installed (ok)\"
  fi
done

if systemctl --user cat frametop-input-relay.service >/dev/null 2>&1; then
  if systemctl --user clean --what=fdstore frametop-input-relay.service 2>/dev/null; then
    say 'frametop-input-relay: cleaned fd store'
  fi
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
echo 'Re-enable the optional 3D mouse later with:'
echo '  pointer/driver/install.sh install && pointer/helper/run.sh install'
echo '  (and desktops.sh relay install if you also disabled the input relay)'
"
