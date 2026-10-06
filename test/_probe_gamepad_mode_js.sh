#!/usr/bin/env bash
# Extract SteamVR JS around EnterDiminishedState / input focus / gamepad mode.
set -u
ssh -o BatchMode=yes steamos@192.168.0.102 bash -s <<'EOF'
python3 - <<'PY'
import pathlib, re
p = pathlib.Path("/opt/steamvr/resources/webinterface/dashboard/chunk~8012d0c89.js")
t = p.read_text(errors="ignore")
for key in [
    "EnterDiminishedState",
    "Diminished",
    "hideDashboard",
    "PushInputFocus",
    "PendingGamepadFocus",
    "SystemPanelInteractionMode",
    "m_eSystemPanelInteractionMode",
    "wBp.Gamepad",
    "InteractionMode",
    "preferGamepadMode",
    "canEnterDiminishedMode",
    "appoverlay",
]:
    print("===== KEY", key, "=====")
    idx = 0
    n = 0
    while n < 3:
        i = t.find(key, idx)
        if i < 0:
            break
        print(t[max(0, i - 120) : i + 220].replace("\n", " "))
        print("---")
        idx = i + len(key)
        n += 1

# Enum dumps
for m in re.finditer(r"e\[e\.([A-Za-z0-9_]+)=(\d+)\]=\"\\1\"", t):
    name, val = m.group(1), m.group(2)
    if any(x in name.lower() for x in ("gamepad", "diminish", "focus", "theater", "interact")):
        print("ENUM", name, val)
PY

echo "=== openvr headers on host ==="
find /opt/steamvr /home/steamos/dev -name 'openvr_api*.h' 2>/dev/null | head -10
find /usr -name 'openvr*.h' 2>/dev/null | head -5
# From repo checkout if synced
if [ -f /home/steamos/dev/frametop/third_party/openvr/headers/openvr.h ]; then
  rg -n "Gamepad|Diminished|desktopgame|SceneApplication" /home/steamos/dev/frametop/third_party/openvr/headers/openvr.h | head -40
fi
EOF
