#!/usr/bin/env bash
set -uo pipefail
python3 - <<'PY'
import json, os, re

p="/home/steamos/.config/openvr/config/steamvr.vrsettings"
print("=== user steamvr.vrsettings eye keys ===")
d=json.load(open(p))
for sec,val in d.items():
  if not isinstance(val, dict):
    continue
  for k,v in val.items():
    if any(x in (sec+k).lower() for x in ("eye","gaze","allow")):
      print(f"  {sec}.{k}={v}")

print("\n=== sniff binding format from binaries ===")
for path in ["/opt/steamvr/bin/linuxarm64/vrclient.so","/opt/steamvr/bin/linuxarm64/vrserver"]:
  data=open(path,"rb").read()
  # find printable strings containing eyetracking near path/output
  text=data.decode("latin1","ignore")
  for m in re.finditer(r"/user/head[^\x00]{0,40}eyetrack[^\x00]{0,40}", text, re.I):
    s=m.group(0)
    if all(32<=ord(c)<127 or c in "\n\t" for c in s):
      print(repr(s)[:120])
  for m in re.finditer(r"[^\x00]{0,30}eyetracking[^\x00]{0,50}", text, re.I):
    s=m.group(0)
    if s.count('"')>=2 and all(32<=ord(c)<127 for c in s):
      print("ctx", repr(s)[:160])

print("\n=== skeletal/pose binding examples near eyetracking parser ===")
# Look in dashboard localization for eye tracking path hints
for root,dirs,files in os.walk("/opt/steamvr/resources"):
  for f in files:
    if not f.endswith(('.json','.js','.txt','.md')): continue
    fp=os.path.join(root,f)
    try:
      s=open(fp,encoding='utf-8',errors='ignore').read()
    except Exception:
      continue
    if 'eyetracking' in s.lower() and ('/user/' in s or 'path' in s):
      print(fp)
      for m in re.finditer(r'.{0,50}eyetrack.{0,80}', s, re.I):
        print(" ", m.group(0).replace("\n"," ")[:140])
PY

echo
echo "=== recent SetActionManifest / binding errors for ft-screens ==="
grep -E 'ft-screens|eyetrack|no configured binding|default_bindings|bindings_frame' \
  /home/steamos/.local/share/Steam/logs/vrserver.txt 2>/dev/null | tail -50
