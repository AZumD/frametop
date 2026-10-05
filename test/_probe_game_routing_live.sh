#!/usr/bin/env bash
# While a Steam game is running: process tree, env hints, SteamVR overlay keys, nested windows.
set -u
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
set +e
echo "=== likely game procs (Hades / proton / reaper) ==="
pgrep -af 'Hades|hades|proton|reaper|steam-launch|pressure-vessel|Capsule' 2>/dev/null | head -40
echo
echo "=== Steam app running markers ==="
ls -la ~/.local/share/Steam/steamapps/common/Hades 2>/dev/null | head -3
# Steam stores running app in some cases via .acf / logs
rg -n --no-heading 'AppID|RunningApp|gameaction|LaunchApp' ~/.local/share/Steam/logs/console_log.txt 2>/dev/null | tail -30
echo
echo "=== recent steam console ==="
tail -40 ~/.local/share/Steam/logs/console_log.txt 2>/dev/null
echo
echo "=== DISPLAY/WAYLAND of hades-like pids ==="
python3 - <<'PY'
import os, glob
keys = ("DISPLAY","WAYLAND_DISPLAY","XDG_RUNTIME_DIR","DBUS_SESSION_BUS_ADDRESS","SteamAppId","SteamGameId","STEAM_COMPAT")
for path in glob.glob("/proc/[0-9]*/cmdline"):
    try:
        cmd = open(path,"rb").read().replace(b"\0", b" ").decode("utf-8","replace")
    except Exception:
        continue
    low = cmd.lower()
    if not any(x in low for x in ("hades", "proton", "reaper", "waitforexitandrun")):
        continue
    if "pgrep" in low or "bash -s" in low:
        continue
    pid = path.split("/")[2]
    envp = f"/proc/{pid}/environ"
    env = {}
    try:
        for e in open(envp,"rb").read().split(b"\0"):
            if b"=" in e:
                k,_,v = e.partition(b"=")
                try: env[k.decode()] = v.decode("utf-8","replace")
                except Exception: pass
    except Exception as ex:
        print(f"pid={pid} cmd={cmd[:120]!r} environ_err={ex}")
        continue
    print(f"--- pid={pid} ---")
    print("cmd:", cmd[:200])
    for k in keys:
        for ek,ev in env.items():
            if ek == k or ek.startswith(k):
                print(f"  {ek}={ev[:160]}")
PY
echo
echo "=== OpenVR / desktopgame overlays (from ft-screens state if up) ==="
python3 - <<'PY'
import socket
s=socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
s.bind(b"\0ft_gr_live")
s.settimeout(2)
for cmd in (b"state", b"toolbar state"):
    try:
        s.sendto(cmd, b"\0ft_screens")
        print(cmd.decode(), "->", s.recv(4096).decode(errors="replace"))
    except Exception as e:
        print(cmd.decode(), "fail", e)
PY
echo
echo "=== nested KWin windows (if desktop up) ==="
# best-effort: use existing helper if synced
if [ -f ~/dev/frametop/test/_kwin_windows.sh ]; then
  bash ~/dev/frametop/test/_kwin_windows.sh 2>/dev/null | head -40
else
  echo "(no _kwin_windows.sh on frame mirror)"
fi
EOF
