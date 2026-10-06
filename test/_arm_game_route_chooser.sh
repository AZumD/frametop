#!/usr/bin/env bash
# Inject steam-ui-patches/game-route/patch.js into SharedJS (temporary CDP path).
# Ultimate home: steamFrame.uiPatches.patches in steam-frame-nix / nix-config.
set -euo pipefail
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
python3 "$ROOT/test/_fix_crlf_tree.py" >/dev/null 2>&1 || true
bash "$ROOT/scripts/sync.sh"
WRAP=${1:-/home/steamos/dev/frametop/session/ft-game-run}
ssh -o BatchMode=yes "$FRAME_HOST" bash -s -- "$WRAP" <<'EOF'
set -euo pipefail
WRAP=$1
repo=/home/steamos/dev/frametop
chmod +x "$repo/session/ft-game-run"
patch=$(cat "$repo/steam-ui-patches/game-route/patch.js")
python3 - "$WRAP" <<'PY'
import json, os, struct, base64, socket, urllib.request, time, sys

WRAP = sys.argv[1]
# Read patch from stdin-less: from file on frame
patch = open("/home/steamos/dev/frametop/steam-ui-patches/game-route/patch.js", encoding="utf-8").read()

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
def ask(method, params=None, timeout=20):
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
# Dispose older probes
ask("Runtime.evaluate", {"expression": "(() => { try{window.__ftGameRouteP2?.dispose?.()}catch(e){}; try{window.__ftGameRouteProbe?.dispose?.()}catch(e){}; try{window.__ftGameRoute?.dispose?.()}catch(e){}; return 'cleared'; })()", "returnByValue": True})

# Provide opts then evaluate patch
prelude = f"window.__ftGameRouteOpts = {json.dumps({'wrapperPath': WRAP, 'enabled': True})};"
res1 = ask("Runtime.evaluate", {"expression": prelude, "returnByValue": True})
res2 = ask("Runtime.evaluate", {"expression": patch, "returnByValue": True})
val = res2.get("result", {}).get("result", {})
if isinstance(val, dict) and val.get("type") in ("string", "object"):
    if "value" in val:
        val = val["value"]
print("patch result:", json.dumps(val, indent=2) if not isinstance(val, str) else val)
res3 = ask("Runtime.evaluate", {"expression": "(() => ({ok:!!window.__ftGameRoute, version:window.__ftGameRoute?.version, armed:window.__ftGameRoute?.dump?.()?.slice(-1)}))()", "returnByValue": True})
val3 = res3.get("result", {}).get("result", {})
if isinstance(val3, dict) and val3.get("type")=="object" and "value" in val3:
    val3 = val3["value"]
print(json.dumps(val3, indent=2))
sock.close()
print("Chooser armed in SharedJS (CDP). Launch a flat game from SteamVR.")
print("Dump: bash test/_dump_game_route_chooser.sh")
print("Disable: evaluate __ftGameRoute.dispose() or bash test/_disarm_game_route_chooser.sh")
PY
EOF
