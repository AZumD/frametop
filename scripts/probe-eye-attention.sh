#!/usr/bin/env bash
# Diagnose the CURRENT ft-screens eye-gaze attention path (not the removed gaze-pointer).
# Read-only. Safe while SteamVR / Frametop desktop are running.
#
# Checks:
#   - screens action/binding manifests next to this checkout and the running binary
#   - recent SteamVR binding / eye errors for ft-screens
#   - recent ft-screens eye/gaze log lines
#   - live "gaze state" from @ft_screens when available
#
# Usage (Frame host or PC over SSH):
#   scripts/probe-eye-attention.sh
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
. "$root/scripts/_env.sh"

on_frame_script "$FRAME_REPO" <<'EOF'
repo=$1
section() { printf '\n===== %s\n' "$*"; }

section "Checkout manifests ($repo/screens)"
for f in actions.json bindings_frame_hmd.json bindings_hmd.json; do
  p="$repo/screens/$f"
  if [ -f "$p" ]; then
    echo "ok $p ($(wc -c < "$p") bytes)"
  else
    echo "MISSING $p"
  fi
done
if command -v python3 >/dev/null; then
  python3 "$repo/test/test_eye_bindings.py" || true
fi

section "Running ft-screens binary + adjacent manifests"
exe=
pid=$(pgrep -nx ft-screens 2>/dev/null || true)
if [ -n "$pid" ]; then
  exe=$(readlink -f "/proc/$pid/exe" 2>/dev/null || true)
  echo "pid=$pid exe=$exe"
else
  echo "ft-screens not running"
fi
if [ -n "$exe" ]; then
  dir=$(dirname "$exe")
  for f in actions.json bindings_frame_hmd.json bindings_hmd.json; do
    if [ -f "$dir/$f" ]; then
      echo "ok $dir/$f"
    else
      echo "MISSING next to binary: $dir/$f"
    fi
  done
fi

section "SteamVR eye / binding log (recent)"
logs=
for d in "$HOME/.local/share/Steam/logs" "$HOME/.steam/steam/logs"; do
  [ -d "$d" ] && logs=$d && break
done
if [ -n "$logs" ]; then
  echo "logs=$logs"
  grep -a -E 'ft-screens|eyetrack|EyeGaze|no configured binding|default_bindings|bindings_frame|SetActionManifest' \
    "$logs/vrserver.txt" 2>/dev/null | tail -n 40 || echo "(no matching vrserver lines)"
else
  echo "Steam logs dir not found"
fi

section "ft-screens eye/gaze log lines"
grep -a -iE 'eye|gaze|manifest|IVRInput|EyeGaze|binding' /tmp/frametop-screens.log 2>/dev/null | tail -n 40 \
  || echo "(no /tmp/frametop-screens.log or no matches)"

section "Live gaze state (@ft_screens)"
python3 - <<'PY' || true
import socket
sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
sock.settimeout(1.5)
try:
    sock.bind("\0")
    sock.sendto(b"gaze state", b"\0ft_screens")
    print(sock.recv(4096).decode(errors="replace"))
except OSError as e:
    print(f"(unavailable: {e})")
finally:
    sock.close()
PY
EOF
