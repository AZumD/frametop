#!/usr/bin/env bash
# Read-only: find SteamVR dashboard strings for flatscreen/gamepad mode.
set -u
ssh -o BatchMode=yes steamos@192.168.0.102 bash -s <<'EOF'
set -u
echo "=== dashboard JS hits ==="
python3 - <<'PY'
import pathlib, re
root = pathlib.Path("/opt/steamvr/resources/webinterface/dashboard")
hits = []
pat = re.compile(
    r".{0,50}(EnterGamepad|GamepadMode|gamepad.?mode|desktopgame|GameTheater|Enter gamepad|gamepadMode|bGamepad).{0,80}",
    re.I,
)
for p in root.rglob("*.js"):
    try:
        t = p.read_text(errors="ignore")
    except OSError:
        continue
    for m in pat.finditer(t):
        hits.append((str(p.name), m.group(0).replace("\n", " ")[:180]))
print("hits", len(hits))
seen = set()
for name, s in hits:
    if s in seen:
        continue
    seen.add(s)
    print(name, ":", s)
    print("---")
    if len(seen) >= 80:
        break
PY
echo "=== strings in vrdashboard / vrcompositor ==="
for bin in /opt/steamvr/bin/linuxarm64/vrdashboard /opt/steamvr/bin/linuxarm64/vrcompositor; do
  [ -f "$bin" ] || continue
  echo "FILE $bin"
  strings "$bin" 2>/dev/null | grep -iE 'desktopgame|gamepad.?mode|GameTheater|EnterGamepad|flat.?screen|gamescope' | sort -u | head -40
done
echo "=== live overlays (helper) ==="
python3 - <<'PY'
import socket, json
try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    s.bind(b"\0ft_gamepad_probe")
    s.settimeout(2)
    s.sendto(b"overlays", b"\0ft_pointer_helper")
    data = s.recv(1 << 20)
    lst = json.loads(data.decode())["list"]
except Exception as e:
    print("overlay list failed:", e)
    raise SystemExit(0)
for e in lst:
    k = e.get("key", "")
    if e.get("visible") or "desktopgame" in k or "gamepad" in k.lower() or "theater" in k.lower():
        if e.get("visible") or "desktopgame" in k or "theater" in k.lower():
            print(("VIS" if e.get("visible") else "hid"), k, e.get("name", ""))
PY
EOF
