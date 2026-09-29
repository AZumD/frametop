#!/usr/bin/env bash
# Probe Frame eye-tracking server state (read-only).
set -euo pipefail

echo "=== eyetracking processes ==="
pgrep -a eyetracking || echo "(none)"
pgrep -a start_eye || echo "(no start_eye)"

echo
echo "=== start_eyetracking references ==="
grep -r start_eyetracking /opt/steamvr \
  --include='*.sh' --include='*.json' --include='*.vrmanifest' \
  --include='*.txt' 2>/dev/null | head -30 || true

echo
echo "=== frame_hmd input_profile eyetracking ==="
python3 - <<'PY'
import json
p="/opt/steamvr/drivers/indexhmd/resources/input/frame_hmd_controller_profile.json"
d=json.load(open(p))
print("keys:", sorted(d.keys()))
inp=d.get("input_source",{})
print("input_source keys:", sorted(inp.keys()))
for k,v in inp.items():
    if "eye" in k.lower() or "gaze" in k.lower() or "track" in k.lower():
        print(k, v)
# also check for eyetracking elsewhere
s=json.dumps(d)
if "eye" in s.lower():
    import re
    for m in re.finditer(r'.{0,40}eye.{0,40}', s, re.I):
        print("ctx:", m.group(0))
PY

echo
echo "=== SteamVR logs (eye) ==="
for f in \
  /home/steamos/.local/share/Steam/logs/vrserver.txt \
  /home/steamos/.steam/steam/logs/vrserver.txt \
  /tmp/SteamVR*/vrserver.txt
do
  if [ -f "$f" ]; then
    echo "-- $f --"
    grep -iE 'eye|gaze|tracking.?server' "$f" 2>/dev/null | tail -40 || true
  fi
done

echo
echo "=== allowEyeTracking + related ==="
python3 - <<'PY'
import json
p="/home/steamos/.local/share/Steam/config/steamvr.vrsettings"
d=json.load(open(p))
for k,v in sorted(d.get("steamvr",{}).items()):
  if any(x in k.lower() for x in ("eye","gaze","track","hmd")):
    print(f"steamvr.{k}={v}")
for sec in d:
  if "eye" in sec.lower() or "gaze" in sec.lower():
    print(sec, d[sec])
PY

echo
echo "=== eyetracking binary help ==="
/opt/steamvr/bin/linuxarm64/eyetracking --help 2>&1 | head -40 || true
