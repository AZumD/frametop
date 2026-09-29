#!/usr/bin/env bash
set -uo pipefail

echo "=== frame_hmd_additional.vrsettings ==="
cat /opt/steamvr/drivers/frame_hmd/resources/frame_hmd_additional.vrsettings

echo
echo "=== find steamvr.vrsettings ==="
find /home/steamos -name 'steamvr.vrsettings' 2>/dev/null
find /home/steamos/.config/openvr -type f 2>/dev/null | head -40
ls -la /home/steamos/.config/openvr/ 2>&1
ls -la /home/steamos/.local/share/Steam/config/ 2>&1 | head -30

echo
echo "=== cv driver eye / gaze ==="
grep -rsl -i 'eye\|gaze' /opt/steamvr/drivers/cv 2>/dev/null | head -30
strings /opt/steamvr/drivers/cv/bin/linuxarm64/driver_cv.so 2>/dev/null | grep -iE 'eyetrack|/input/eye|Gaze|allowEye' | head -40

echo
echo "=== openvr strings eye paths ==="
strings /opt/steamvr/bin/linuxarm64/vrclient.so 2>/dev/null | grep -iE 'eyetrack|/input/eye|EyeGaze|GetEyeTracking' | head -40
strings /opt/steamvr/bin/linuxarm64/vrserver 2>/dev/null | grep -iE 'eyetrack|/input/eye|allowEye' | head -40

echo
echo "=== hellovr or samples with eye ==="
find /opt/steamvr -iname '*eye*' 2>/dev/null | head -40
grep -rsl 'GetEyeTracking\|type": "eyetracking"' /opt/steamvr/samples /opt/steamvr/tools /opt/steamvr/resources 2>/dev/null | head -20

echo
echo "=== controllerbindingui eyetracking snippet ==="
grep -o '.{0,80}eyetrack.{0,80}' /opt/steamvr/resources/webinterface/dashboard/controllerbindingui.js 2>/dev/null | head -20
# python extract
python3 - <<'PY'
import re
p="/opt/steamvr/resources/webinterface/dashboard/controllerbindingui.js"
try:
  s=open(p,encoding='utf-8',errors='ignore').read()
except Exception as e:
  print(e); raise SystemExit
for m in re.finditer(r'.{0,60}eyetrack.{0,80}', s, re.I):
  print(m.group(0).replace('\n',' '))
  if m.start()>500000: break
print('count', len(re.findall('eyetrack', s, re.I)))
PY

echo
echo "=== ft-screens app key / openvr apps ==="
grep -iE 'ft-screens|frametop|SetActionManifest|binding' /tmp/frametop-screens.log 2>/dev/null | tail -40
grep -iE 'ft-screens|frametop' /home/steamos/.local/share/Steam/logs/vrserver.txt 2>/dev/null | tail -40
