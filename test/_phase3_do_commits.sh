#!/usr/bin/env bash
# Selective Phase 3 commits; preserve launcher/instrument WIP in layout + display-settings.
set -euo pipefail
cd /mnt/c/Users/Antho/Projects/frametop-customized-main

# --- preserve mixed WIP ---
cp layout/ft_layout.py /tmp/ft_layout.wip.py
git show HEAD:layout/ft_layout.py > layout/ft_layout.py
python3 - <<'PY'
from pathlib import Path
p = Path("layout/ft_layout.py")
t = p.read_text(encoding="utf-8")
old = '''def outputs(env):
    """KWin's outputs, in screen order (WL-0, WL-1, ...)."""
    try:
        data = json.loads(subprocess.run(["kscreen-doctor", "-j"], capture_output=True, text=True, env=env,
                                         timeout=10).stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []
    outs = [o for o in data.get("outputs", []) if o.get("connected")]
    return sorted(outs, key=lambda o: [int(t) if t.isdigit() else t for t in re.split(r"(\\d+)", o.get("name", ""))])
'''
new = '''def outputs(env):
    """KWin's outputs for the screens, in screen order (WL-0, WL-1, ...).

    Outputs after the configured screen count are spares for floating windows
    (ft-floatd places them). Layout must never rearrange those.
    """
    try:
        data = json.loads(subprocess.run(["kscreen-doctor", "-j"], capture_output=True, text=True, env=env,
                                         timeout=10).stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []
    outs = [o for o in data.get("outputs", []) if o.get("connected")]
    if backend() == "screens":
        count = screen_count()
        outs = [o for o in outs if not re.fullmatch(r"WL-(\\d+)", o.get("name", "")) or
                int(o["name"][3:]) < count]
    return sorted(outs, key=lambda o: [int(t) if t.isdigit() else t for t in re.split(r"(\\d+)", o.get("name", ""))])
'''
if old not in t:
    raise SystemExit("HEAD outputs() not found for float-only patch")
p.write_text(t.replace(old, new, 1), encoding="utf-8")
print("layout float-only patch applied")
PY

# Sanity: no instrument desktop hunk in staged layout
if grep -n 'Join remaining argv' layout/ft_layout.py; then
  echo "ERROR: WIP leaked into layout float-only tree" >&2
  exit 1
fi

msg1=$(cat <<'EOF'
Add floating-window daemon and KWin integration

Spare KWin outputs, ft-floatd, the float script, decoration, and session wiring
give floating windows their own panels without layout rearranging spares.
EOF
)

git add \
  float/ \
  decoration/ \
  docs/floating-windows.md \
  docs/README/FT_FLOATD.md \
  docs/README/FT_APPS.md \
  session/frametop-session.sh \
  session/frametop.conf.example \
  layout/ft_layout.py
git diff --cached --stat
git commit -m "$msg1"
echo "COMMIT1=$(git rev-parse --short HEAD)"

msg2=$(cat <<'EOF'
Render floating windows as independent VR panels

ft-screens --spares creates frametop.float.N overlays with crop, sub-overlays,
fullscreen/minimize, and catcher-backed release so floats are not real screens.
EOF
)

git add \
  screens/compositor.c \
  screens/vr.cpp \
  screens/vr.h \
  screens/test/headless.sh \
  docs/README/SCREENS_TEST_HEADLESS.md \
  test/test_float_screens_wiring.py
git diff --cached --stat
git commit -m "$msg2"
echo "COMMIT2=$(git rev-parse --short HEAD)"

msg3=$(cat <<'EOF'
Add float/dock actions and pointer float targeting

Meta+Shift+F toggles float/dock via the input relay; the pointer treats
frametop.float.* as FramePanels and sends up on release without importing gaze.
EOF
)

git add \
  pointer/helper/ft-pointer.cpp \
  input/input-relay.py \
  input-settings/ft_input_settings.py \
  docs/README/INPUT-RELAY.md \
  docs/README/FT_POINTER.md \
  docs/README/OVERVIEW.md \
  test/test_float_phase3.py \
  test/test_vr_keyboard_relay.py
git diff --cached --stat
git commit -m "$msg3"
echo "COMMIT3=$(git rev-parse --short HEAD)"

# Restore full WIP layout (instrument launcher hunks + float filter)
cp /tmp/ft_layout.wip.py layout/ft_layout.py
# float filter is already in WIP copy; verify
grep -n 'spares for floating' layout/ft_layout.py >/dev/null

echo "==== post-commit status ===="
git status --short
git log --oneline be81a4e..HEAD
