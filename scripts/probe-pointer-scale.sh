#!/usr/bin/env bash
# Read-only: pointer scale diagnosis on the Frame.
set -uo pipefail

echo "=== layout scales ==="
python3 - <<'PY'
import json
p="/home/steamos/.config/frametop-layout.json"
d=json.load(open(p))
for i,s in enumerate(d.get("screens",[])):
  print(f"screen{i+1}: size={s.get('size')} scale={s.get('scale')} metres={s.get('metres')}")
PY

echo
echo "=== ft-screens log (buffer/surface) ==="
grep -E 'buffer |surface |commit' /tmp/frametop-screens.log 2>/dev/null | tail -40

echo
echo "=== kwin outputs ==="
qdbus org.kde.KWin /KWin org.kde.KWin.showDebugConsole 2>/dev/null | head -1 || true
# kscreen-doctor if available
kscreen-doctor -o 2>/dev/null | head -80 || true
# fallback: kwin remote
python3 - <<'PY'
import json,subprocess,os
# try reading from kwin via qdbus-qt6 / dbus
for cmd in [
  ["kscreen-doctor","-o"],
]:
  try:
    r=subprocess.run(cmd,capture_output=True,text=True,timeout=5)
    if r.returncode==0:
      print(r.stdout[:3000])
      break
  except Exception as e:
    print(cmd, e)
PY

echo
echo "=== running ft-screens binary age vs coords ==="
ls -la /home/steamos/frametop/screens/build/ft-screens /home/steamos/frametop/screens/coords.h
strings /home/steamos/frametop/screens/build/ft-screens | grep -E 'ft_buffer_to_surface|surface %dx%d|buffer %dx%d' | head
pgrep -a ft-screens
# Does running binary include surface size tracking?
python3 - <<'PY'
import os,subprocess
# compare mtime of binary vs process start
import time
st=os.stat("/home/steamos/frametop/screens/build/ft-screens")
print("binary mtime", time.ctime(st.st_mtime))
PY
ps -o lstart= -p $(pgrep -x ft-screens) 2>/dev/null || true
