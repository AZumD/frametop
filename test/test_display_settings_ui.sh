#!/usr/bin/env bash
# Smoke-check Display Settings visibility mode + tab order + instruments grid.
#   bash test/test_display_settings_ui.sh
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
fail=0
ok() { echo "ok: $*"; }
bad() { echo "FAIL: $*" >&2; fail=1; }
has() { grep -q -- "$1" "$2" && ok "has $1 in $(basename "$2")" || bad "missing $1 in $2"; }

qml="$root/display-settings/main.qml"
vr="$root/screens/vr.cpp"
py="$root/display-settings/ft_display_settings.py"

has 'except_dashboard' "$qml"
has 'Hide whenever the SteamVR dashboard opens' "$qml"
has 'Mode::ExceptDashboard' "$vr"
has 'except_dashboard' "$vr"

# Tab order: Screens, Layout, Visibility, Background, Spatial Instruments
python3 - <<PY
import re, sys
qml = open(r"""$qml""", encoding="utf-8").read()
# Extract the screens-backend pages list
m = re.search(r'backend\.backend === "screens"\s*\?\s*\[(.*?)\]\s*:', qml, re.S)
if not m:
    print("FAIL: pages list not found", file=sys.stderr); sys.exit(1)
block = m.group(1)
texts = re.findall(r'text:\s*"([^"]+)"', block)
want = ["Screens", "Layout", "Visibility", "Background", "Spatial Instruments"]
if texts != want:
    print("FAIL: tab order", texts, "!=", want, file=sys.stderr); sys.exit(1)
print("ok: tab order", " > ".join(texts))
PY

has 'Kirigami.AbstractCard' "$qml"
has 'PreviewPlate' "$qml"
has 'Seven-segment HH:MM' "$qml"
has 'Configure…' "$qml"
has 'Built-in' "$qml"
has 'drawDigit' "$qml"

# Instrument Configure uses a pushed page (Dialog opened empty on the Frame).
# Restart confirmation still legitimately uses Kirigami.Dialog.
has 'id: instrumentEditPage' "$qml"
has 'pageStack.push(instrumentEditPage)' "$qml"
has 'title: "Restart the desktop?"' "$qml"
if grep -q 'id: editSheet' "$qml"; then
  bad "obsolete editSheet Dialog still present"
else
  ok "no obsolete editSheet Dialog"
fi

if [ "$fail" -ne 0 ]; then
  echo "display-settings UI checks failed" >&2
  exit 1
fi
echo "all display-settings UI checks passed"
