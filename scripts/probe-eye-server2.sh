#!/usr/bin/env bash
# Continue eye-tracking diagnosis (read-only). Absolute paths only.
set -uo pipefail

HOME_STEAM=/home/steamos

echo "=== whoami / home ==="
whoami
echo "HOME=$HOME"

echo
echo "=== find frame_hmd profile ==="
find /opt/steamvr/drivers/frame_hmd -type f 2>/dev/null | head -60

echo
echo "=== eyetracking paths under steamvr ==="
find /opt/steamvr -iname '*eyetrack*' 2>/dev/null | head -40

echo
echo "=== grep eyetracking in frame_hmd driver ==="
grep -rsl 'eyetrack\|/input/eye' /opt/steamvr/drivers/frame_hmd 2>/dev/null | head -30
grep -n 'eye\|gaze\|track' /opt/steamvr/drivers/frame_hmd/resources/input/* 2>/dev/null | head -40

echo
echo "=== frame_hmd input profile json ==="
find /opt/steamvr/drivers/frame_hmd -name '*profile*' -o -name '*input*.json' 2>/dev/null | head -20
for f in /opt/steamvr/drivers/frame_hmd/resources/input/*.json; do
  echo "-- $f --"
  python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(json.dumps(d, indent=2)[:3000])" "$f" 2>/dev/null | head -80
done

echo
echo "=== allowEyeTracking ==="
python3 - <<'PY'
import json, os
for p in [
  "/home/steamos/.local/share/Steam/config/steamvr.vrsettings",
  "/home/steamos/.steam/steam/config/steamvr.vrsettings",
]:
  if os.path.isfile(p):
    d=json.load(open(p))
    print("file", p)
    for k,v in sorted(d.get("steamvr",{}).items()):
      if any(x in k.lower() for x in ("eye","gaze","track","hmd","allow")):
        print(f"  steamvr.{k}={v}")
    for sec,val in d.items():
      if any(x in sec.lower() for x in ("eye","gaze","frame")):
        print(sec, val)
PY

echo
echo "=== frametop screens sources/build ==="
ls -la "$HOME_STEAM/frametop/screens/" 2>&1 | head -40
ls -la "$HOME_STEAM/frametop/screens/build/" 2>&1 | head -40
ls -la "$HOME_STEAM/dev/frametop/screens/" 2>&1 | head -40

echo
echo "=== OpenVR app bindings for frametop ==="
find "$HOME_STEAM" -iname '*frametop*' 2>/dev/null | head -40
find "$HOME_STEAM/.local/share/Steam" -iname '*binding*' 2>/dev/null | head -30

echo
echo "=== ft-screens log eye lines ==="
grep -iE 'eye|gaze|manifest|binding' /tmp/frametop-screens.log 2>/dev/null | tail -40 || true

echo
echo "=== eyetracking process + help ==="
pgrep -a eyetracking || echo "(none)"
ET=/opt/steamvr/tools/eyetracking/bin/linuxarm64/eyetracking
ls -la "$ET" 2>/dev/null || true
"$ET" --help 2>&1 | head -40 || true

echo
echo "=== gaze state now ==="
"$HOME_STEAM/frametop/layout/ft-layout" gaze state 2>&1 || true
