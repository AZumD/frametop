#!/usr/bin/env bash
set -uo pipefail

echo "=== steamvr eye refs ==="
grep -rsl -i 'eyetrack\|EyeTracking\|allowEye' /opt/steamvr 2>/dev/null | head -60

echo
echo "=== steamvr.vrsettings ==="
python3 - <<'PY'
import json, os
p="/home/steamos/.local/share/Steam/config/steamvr.vrsettings"
print("exists", os.path.isfile(p))
if os.path.isfile(p):
  d=json.load(open(p))
  print("sections", list(d.keys()))
  sv=d.get("steamvr",{})
  for k,v in sorted(sv.items()):
    kl=k.lower()
    if any(x in kl for x in ("eye","gaze","track","allow","hmd","input")):
      print(f"  steamvr.{k}={v}")
  # print all keys that look relevant
  for sec,val in d.items():
    if isinstance(val, dict):
      for k,v in val.items():
        if any(x in (sec+k).lower() for x in ("eye","gaze")):
          print(f"  {sec}.{k}={v}")
PY

echo
echo "=== other HMDs with eyetracking input_source ==="
grep -rsl '"eyetracking"\|/input/eyetracking' /opt/steamvr/drivers 2>/dev/null | head -40
for f in $(grep -rsl '/input/eyetracking\|"type": "eyetracking"' /opt/steamvr 2>/dev/null | head -20); do
  echo "-- $f --"
  grep -n -i 'eye' "$f" | head -20
done

echo
echo "=== Frame vr.cpp eye bits ==="
grep -n 'eye\|Eye\|gaze\|GetEye\|SetActionManifest\|GetActionHandle\|default_bindings\|bindings_' \
  /home/steamos/frametop/screens/vr.cpp | head -60

echo
echo "=== Frame screens dir (bindings?) ==="
ls -la /home/steamos/frametop/screens/

echo
echo "=== persist eyetracking config ==="
ls -la /persist/eyetracking.json /home/steamos/.config/eyetracking.json 2>&1
cat /persist/eyetracking.json 2>&1 | head -50

echo
echo "=== start_eyetracking.sh ==="
cat /opt/steamvr/bin/linuxarm64/start_eyetracking.sh

echo
echo "=== openvr IVRInput eye symbols in lib ==="
nm -D /opt/steamvr/bin/linuxarm64/libopenvr_api.so 2>/dev/null | grep -i eye | head -30
strings /opt/steamvr/bin/linuxarm64/libopenvr_api.so 2>/dev/null | grep -i 'eyetrack\|/input/eye' | head -30

echo
echo "=== vrclient / vrserver recent eye log ==="
for f in /home/steamos/.local/share/Steam/logs/vrserver.txt \
         /home/steamos/.local/share/Steam/logs/vrclient_*.txt; do
  [ -f "$f" ] || continue
  if grep -qi eye "$f" 2>/dev/null; then
    echo "-- $f --"
    grep -i eye "$f" | tail -15
  fi
done
