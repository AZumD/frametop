#!/usr/bin/env bash
# Probe Frame layout profiles: store, current layout screen count, apply smoke.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
. "$root/scripts/_env.sh"

ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
set +e
echo "=== profiles file ==="
python3 - <<'PY'
import json, os
p = os.path.expanduser("~/.config/frametop-layout-profiles.json")
print("path", p, "exists", os.path.exists(p))
if os.path.exists(p):
    data = json.load(open(p))
    print("current:", data.get("current"))
    print("slots:", data.get("slots"))
    profiles = data.get("profiles") or {}
    print("names:", sorted(profiles))
    for name, prof in sorted(profiles.items()):
        screens = (prof or {}).get("screens") or []
        inst = (prof or {}).get("instruments")
        print(f"  {name!r}: screens={len(screens)} instruments={'missing' if inst is None else len(inst)}")
        if screens:
            s0 = screens[0]
            print(f"    screen0 keys={sorted(s0)} pos={s0.get('pos')} pin={s0.get('pin')}")
PY

echo "=== active layout ==="
python3 - <<'PY'
import json, os
p = os.path.expanduser("~/.config/frametop-layout.json")
print("path", p, "exists", os.path.exists(p))
if os.path.exists(p):
    data = json.load(open(p))
    print("mode:", data.get("mode"), "screens:", len(data.get("screens") or []))
    print("keys:", sorted(data.keys()))
    for i, s in enumerate(data.get("screens") or []):
        print(f"  screen{i+1}: pos={s.get('pos')} metres={s.get('metres')} pin={s.get('pin')} hidden={s.get('hidden')}")
PY

echo "=== ft-layout profile list / current ==="
~/dev/frametop/layout/ft-layout profile list 2>&1
~/dev/frametop/layout/ft-layout profile current 2>&1
~/dev/frametop/layout/ft-layout profile slots 2>&1

echo "=== desktop / screens ==="
pgrep -x ft-screens >/dev/null && echo screens_running || echo screens_down
ls -l /proc/$(pgrep -x ft-screens | head -1)/exe 2>/dev/null | head -1
EOF
