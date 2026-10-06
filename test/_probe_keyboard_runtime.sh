#!/usr/bin/env bash
# Diagnose why Frametop's VR keyboard doesn't open on text-field focus.
set -euo pipefail

echo "=== rules: vr_keyboard ==="
python3 - <<'PY'
import json, os
p = os.path.expanduser("~/.config/frametop-input.json")
try:
    r = json.load(open(p))
except Exception as e:
    print(f"unreadable {p}: {e}")
    r = {}
print("file:", p)
print("vr_keyboard:", r.get("vr_keyboard", "<missing → default no_keyboard>"))
print("vr_keyboard_persist:", r.get("vr_keyboard_persist", "<missing → default true>"))
PY

echo
echo "=== pass-through keyboards (why no_keyboard may stay closed) ==="
# Ask the live relay if it's up
python3 - <<'PY'
import os, socket, json
s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
s.settimeout(1.0)
s.bind(f"\0ft_kb_probe_{os.getpid()}")
try:
    s.sendto(b"devices", b"\0frametop_relay")
    data, _ = s.recvfrom(65535)
    msg = json.loads(data)
    for d in msg.get("devices", []):
        kinds = d.get("kinds") or []
        if "keyboard" not in kinds:
            continue
        print(f"  role={d.get('role')} uinput={d.get('uinput')} connected={d.get('connected')} name={d.get('name')!r}")
except Exception as e:
    print(f"relay devices: {e}")
finally:
    s.close()
PY

echo
echo "=== ft-textinput / session ==="
pgrep -af 'ft-textinput' || echo "ft-textinput NOT running"
pgrep -af 'ft-screens' || echo "ft-screens NOT running"
pgrep -af 'frametop-input-relay|input-relay' || echo "relay NOT running"

echo
echo "=== session XIM scrub (script on disk) ==="
grep -n 'QT_IM_MODULE\|GTK_IM_MODULE\|inputmethod\|ft-textinput' ~/dev/frametop/session/frametop-session.sh | head -30

echo
echo "=== ft-screens knows vrkeyboard? ==="
# ask via abstract socket if present
python3 - <<'PY'
import os, socket
s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
s.settimeout(1.0)
s.bind(f"\0ft_kb_ask_{os.getpid()}")
for sock in (b"\0ft_screens", b"\0ft_screens-0"):
    try:
        s.sendto(b"vrkeyboard toggle", sock)
        data, _ = s.recvfrom(4096)
        print(sock, "->", data.decode(errors="replace"))
        break
    except Exception as e:
        print(sock, "fail", e)
else:
    print("no ft_screens reply")
s.close()
PY

echo
echo "=== built keyboard into ft-screens? ==="
ls -la ~/dev/frametop/screens/build/ft-screens 2>/dev/null || echo "no build/ft-screens"
ls -la ~/dev/frametop/screens/keyboard.cpp 2>/dev/null || echo "no keyboard.cpp"
# strings check if binary exists
if [ -x ~/dev/frametop/screens/build/ft-screens ]; then
  strings ~/dev/frametop/screens/build/ft-screens | grep -E 'vrkeyboard|frametop.keyboard|keyboard:' | head -20 || echo "no keyboard strings in binary"
fi
# also check the running binary path
ps -o args= -C ft-screens 2>/dev/null | head -3 || true
bin=$(readlink -f /proc/$(pgrep -nx ft-screens 2>/dev/null || echo)/exe 2>/dev/null || true)
echo "running exe: ${bin:-unknown}"
if [ -n "${bin:-}" ] && [ -x "$bin" ]; then
  strings "$bin" | grep -E 'vrkeyboard|frametop.keyboard' | head -10 || echo "running binary has no keyboard strings"
fi

echo
echo "=== recent relay / screens logs (textfield|vrkeyboard|keyboard) ==="
for f in /tmp/frametop-screens.log /tmp/frametop-session.log; do
  [ -f "$f" ] || continue
  echo "-- $f"
  grep -iE 'textfield|vrkeyboard|keyboard|ft-textinput|inputmethod' "$f" | tail -20 || true
done
journalctl --user -u frametop-input-relay.service --no-pager -n 80 2>/dev/null | grep -iE 'textfield|vrkeyboard|keyboard|error' | tail -30 || true
