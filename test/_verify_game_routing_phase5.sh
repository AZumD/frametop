#!/usr/bin/env bash
# Phase 5 verify: ft-game-run log, game DISPLAY, nested KWin windows, Steam status; restore options.
set -u
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
set +e
echo "=== ft-game-run log ==="
tail -30 /tmp/frametop-game-run.log 2>/dev/null || echo "(no log yet)"

echo
echo "=== Hades procs + DISPLAY ==="
python3 - <<'PY'
import glob
for path in glob.glob("/proc/[0-9]*/cmdline"):
    try:
        cmd = open(path,"rb").read().replace(b"\0", b" ").decode("utf-8","replace")
    except Exception:
        continue
    if "Hades.exe" not in cmd and "AppId=1145360" not in cmd:
        continue
    if "pgrep" in cmd: continue
    pid = path.split("/")[2]
    env = {}
    try:
        for e in open(f"/proc/{pid}/environ","rb").read().split(b"\0"):
            if b"=" in e:
                k,_,v=e.partition(b"=")
                env[k.decode()]=v.decode("utf-8","replace")
    except Exception as ex:
        print(pid, "env_err", ex); continue
    print(f"pid={pid} DISPLAY={env.get('DISPLAY')} WAYLAND={env.get('WAYLAND_DISPLAY')} XDG_RUNTIME_DIR={env.get('XDG_RUNTIME_DIR')} XAUTHORITY={env.get('XAUTHORITY','')[:60]}")
    print("  cmd:", cmd[:160])
PY

echo
echo "=== nested KWin normal windows ==="
export XDG_RUNTIME_DIR=/run/user/$(id -u)/frametop
export DBUS_SESSION_BUS_ADDRESS=$(tr '\0' '\n' < /run/user/$(id -u)/frametop/plasmashell.env 2>/dev/null | awk -F= '$1=="DBUS_SESSION_BUS_ADDRESS"{print substr($0,index($0,"=")+1); exit}')
# One-shot KWin script if qdbus available
if command -v qdbus >/dev/null && [ -n "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
  script='print("FTWIN_BEGIN"); var ws=workspace.windowList(); for (var i=0;i<ws.length;++i){ var w=ws[i]; if(!w.normalWindow) continue; print("FTWIN id="+w.internalId+" cls="+w.resourceClass+" cap="+w.caption+" out="+(w.output?w.output.name:"?")+" full="+w.fullScreen); } print("FTWIN_END");'
  # Prefer kwin scripting loadScript if available — fall back to ft-taskbar style
  python3 - <<'PY' 2>/dev/null || true
import os, subprocess, textwrap, tempfile, time
# Use ft-taskbar's approach if present
repo="/home/steamos/dev/frametop"
# minimal: ask kwin via dbus org.kde.KWin /Scripting
js = r'''
print("FTWIN_BEGIN");
var ws = workspace.windowList();
for (var i = 0; i < ws.length; ++i) {
  var w = ws[i];
  if (!w.normalWindow) continue;
  var out = "?";
  try { out = w.output ? w.output.name : "?"; } catch(e) {}
  print("FTWIN cls=" + w.resourceClass + " cap=" + w.caption + " out=" + out + " full=" + w.fullScreen);
}
print("FTWIN_END");
'''
path = "/tmp/ft-kwin-list.js"
open(path,"w").write(js)
env = os.environ.copy()
# loadScript
try:
    num = subprocess.check_output(
        ["qdbus", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.loadScript", path],
        env=env, text=True, timeout=5).strip()
    subprocess.check_call(["qdbus", "org.kde.KWin", f"/Scripting/Script{num}", "org.kde.kwin.Script.run"], env=env, timeout=5)
    time.sleep(0.3)
    subprocess.call(["qdbus", "org.kde.KWin", f"/Scripting/Script{num}", "org.kde.kwin.Script.stop"], env=env, timeout=5)
except Exception as e:
    print("kwin script fail", e)
PY
  # journal / kwin may print elsewhere — also try reading from plasmashell journal
  journalctl --user -n 50 --no-pager 2>/dev/null | grep FTWIN | tail -20 || true
else
  echo "(no nested dbus / qdbus)"
fi

echo
echo "=== Steam console last Hades lines ==="
rg -n --no-heading '1145360' ~/.local/share/Steam/logs/console_log.txt 2>/dev/null | tail -25

echo
echo "=== launch options marker ==="
cat /run/user/$(id -u)/frametop-game-route/launch-options-backup.json 2>/dev/null || echo "(none)"
EOF

# Always attempt restore after verify so we never leave options mutated.
bash "$ROOT/test/_restore_game_launch_options.sh" || true
