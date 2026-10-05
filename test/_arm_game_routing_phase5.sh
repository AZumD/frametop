#!/usr/bin/env bash
# Phase 5 prep: sync ft-game-run, set temporary launch options wrap for one app.
# Does NOT cancel launches — user does a normal SteamVR launch after this.
# Always pair with _restore_game_launch_options.sh (verify script restores too).
set -euo pipefail
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
APP_ID="${1:-1145360}"
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
python3 "$ROOT/test/_fix_crlf_tree.py" >/dev/null 2>&1 || true
bash "$ROOT/scripts/sync.sh"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s -- "$APP_ID" <<'EOF'
set -euo pipefail
APP_ID=$1
repo=/home/steamos/dev/frametop
wrap="$repo/session/ft-game-run"
marker_dir=/run/user/$(id -u)/frametop-game-route
marker=$marker_dir/launch-options-backup.json
envf=/run/user/$(id -u)/frametop/plasmashell.env

chmod +x "$wrap" "$wrap.py" 2>/dev/null || chmod +x "$wrap"
test -f "$envf" || { echo "FAIL: no plasmashell.env — start Frametop desktop first"; exit 1; }

python3 - <<PY
import sys
sys.path.insert(0, "$repo/session")
from ft_game_run import nested_display_overrides, plasmashell_env_path, summarize_env
ov = nested_display_overrides()
print("overrides:", summarize_env(ov))
print("env_file:", plasmashell_env_path())
print("wrapper:", "$wrap")
PY

echo "=== install temporary launch options via SharedJS ==="
python3 - "$APP_ID" "$wrap" "$marker" "$repo/session" <<'PY'
import json, os, struct, base64, socket, urllib.request, time, sys

APP_ID = int(sys.argv[1])
WRAP = sys.argv[2]
MARKER = sys.argv[3]
sys.path.insert(0, sys.argv[4])
from ft_game_run import wrap_launch_options, already_wrapped

def http_json(url):
    return json.loads(urllib.request.urlopen(url, timeout=3).read())

shared = next(t for t in http_json("http://127.0.0.1:8080/json/list") if (t.get("title") or "") == "SharedJSContext")
ws_url = shared["webSocketDebuggerUrl"]
hostport, path = ws_url[5:].split("/", 1)
host, port = hostport.split(":")
port = int(port)
path = "/" + path
key = base64.b64encode(os.urandom(16)).decode()
req = (f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode()
sock = socket.create_connection((host, port), timeout=5)
sock.sendall(req)
buf = b""
while b"\r\n\r\n" not in buf:
    buf += sock.recv(4096)
header, rest = buf.split(b"\r\n\r\n", 1)

def recv_frame(leftover=b""):
    data = leftover
    while len(data) < 2:
        data += sock.recv(4096)
    b1, b2 = data[0], data[1]
    ln = b2 & 0x7f
    idx = 2
    if ln == 126:
        while len(data) < idx+2: data += sock.recv(4096)
        ln = struct.unpack("!H", data[idx:idx+2])[0]; idx += 2
    elif ln == 127:
        while len(data) < idx+8: data += sock.recv(4096)
        ln = struct.unpack("!Q", data[idx:idx+8])[0]; idx += 8
    while len(data) < idx+ln: data += sock.recv(max(4096, ln))
    return b1 & 0x0f, data[idx:idx+ln], data[idx+ln:]

def send_text(s):
    payload = s.encode(); header = bytearray([0x81]); n=len(payload); mask_bit=0x80
    if n < 126: header.append(mask_bit|n)
    elif n < 65536: header.append(mask_bit|126); header += struct.pack("!H", n)
    else: header.append(mask_bit|127); header += struct.pack("!Q", n)
    mask = os.urandom(4); header += mask
    sock.sendall(bytes(header)+bytes(b^mask[i%4] for i,b in enumerate(payload)))

leftover = rest
mid = 0
def ask(method, params=None, timeout=12):
    global mid, leftover
    mid += 1
    msg={"id":mid,"method":method}
    if params is not None: msg["params"]=params
    send_text(json.dumps(msg))
    deadline=time.time()+timeout
    while time.time()<deadline:
        opcode, payload, leftover = recv_frame(leftover)
        if opcode!=1: continue
        data=json.loads(payload)
        if data.get("id")==mid: return data
    raise TimeoutError(method)

ask("Runtime.enable")
ask("Runtime.evaluate", {
    "expression": "(() => { try { window.__ftGameRouteP2?.dispose?.(); } catch(e){} return 'ok'; })()",
    "returnByValue": True,
})

# Read current options
expr_get = f"""
(async () => {{
  const Apps = SteamClient.Apps;
  const appId = {APP_ID};
  const details = await new Promise((resolve, reject) => {{
    let done=false;
    const t=setTimeout(()=>{{ if(!done){{done=true; reject(new Error('details timeout'));}}}}, 4000);
    const u = Apps.RegisterForAppDetails(appId, (d) => {{
      if(done) return; done=true; clearTimeout(t);
      try {{ u?.unregister?.() ?? u?.(); }} catch {{}}
      resolve({{ strLaunchOptions: d.strLaunchOptions || '', strDisplayName: d.strDisplayName, eDisplayStatus: d.eDisplayStatus }});
    }});
  }});
  return details;
}})()
"""
res = ask("Runtime.evaluate", {"expression": expr_get, "returnByValue": True, "awaitPromise": True}, timeout=15)
val = res.get("result", {}).get("result", {})
if isinstance(val, dict) and val.get("type")=="object" and "value" in val:
    val = val["value"]
original = (val or {}).get("strLaunchOptions") or ""
name = (val or {}).get("strDisplayName")
status = (val or {}).get("eDisplayStatus")

if already_wrapped(original, WRAP):
    next_opts = original
    changed = False
else:
    next_opts = wrap_launch_options(original, WRAP)
    expr_set = f"""
(async () => {{
  await SteamClient.Apps.SetAppLaunchOptions({APP_ID}, {json.dumps(next_opts)});
  return 'set';
}})()
"""
    ask("Runtime.evaluate", {"expression": expr_set, "returnByValue": True, "awaitPromise": True})
    changed = True

os.makedirs(os.path.dirname(MARKER), exist_ok=True)
backup = {"appId": APP_ID, "original": original, "installed": next_opts, "ts": time.time(), "name": name}
with open(MARKER, "w", encoding="utf-8") as f:
    json.dump(backup, f, indent=2)

print(json.dumps({"name": name, "status": status, "original": original, "installed": next_opts, "changed": changed, "marker": MARKER}, indent=2))
sock.close()
print("READY: launch the game once from SteamVR.")
print("Then: bash test/_verify_game_routing_phase5.sh")
print("Emergency restore: bash test/_restore_game_launch_options.sh")
PY
EOF
