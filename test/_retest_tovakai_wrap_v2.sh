#!/usr/bin/env bash
# Fully automate Tovakai wrap (patch v5+): arm → steam://run → pick tovakai → verify.
set -euo pipefail
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
APP_ID=${1:-1145360}

echo "=== ensure Hades not running ==="
ssh -o BatchMode=yes "$FRAME_HOST" 'pkill -f Hades.exe 2>/dev/null || true; sleep 2; rm -f /tmp/frametop-game-run.log; echo stopped' || true

echo "=== re-arm chooser ==="
bash "$ROOT/test/_arm_game_route_chooser.sh"

echo "=== trigger steam://run/$APP_ID then CDP-pick tovakai ==="
ssh -o BatchMode=yes "$FRAME_HOST" bash -s -- "$APP_ID" <<'EOF'
set -euo pipefail
APP_ID=$1
python3 - "$APP_ID" <<'PY'
import json, os, struct, base64, socket, urllib.request, time, sys
APP_ID = sys.argv[1]

def http_json(url):
    return json.loads(urllib.request.urlopen(url, timeout=3).read())

def connect():
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
    return sock, rest

def recv_frame(sock, leftover=b""):
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

def send_text(sock, s):
    payload = s.encode(); header = bytearray([0x81]); n=len(payload); mask_bit=0x80
    if n < 126: header.append(mask_bit|n)
    elif n < 65536: header.append(mask_bit|126); header += struct.pack("!H", n)
    else: header.append(mask_bit|127); header += struct.pack("!Q", n)
    mask = os.urandom(4); header += mask
    sock.sendall(bytes(header)+bytes(b^mask[i%4] for i,b in enumerate(payload)))

sock, leftover = connect()
mid = 0

def ask(method, params=None, timeout=20):
    global mid, leftover
    mid += 1
    msg={"id":mid,"method":method}
    if params is not None: msg["params"]=params
    send_text(sock, json.dumps(msg))
    deadline=time.time()+timeout
    while time.time()<deadline:
        opcode, payload, leftover = recv_frame(sock, leftover)
        if opcode!=1: continue
        data=json.loads(payload)
        if data.get("id")==mid: return data
    raise TimeoutError(method)

def eval_expr(expr, timeout=20):
    res = ask("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True}, timeout=timeout)
    if res.get("result", {}).get("exceptionDetails"):
        return {"__exception": res["result"]["exceptionDetails"]}
    val = res.get("result", {}).get("result", {})
    if isinstance(val, dict) and val.get("type")=="object" and "value" in val:
        val = val["value"]
    elif isinstance(val, dict) and val.get("type") in ("string","number","boolean") and "value" in val:
        val = val["value"]
    return val

ask("Runtime.enable")
armed = eval_expr("!!window.__ftGameRoute && window.__ftGameRoute.version")
print("armed_version=", armed)
if not armed:
    raise SystemExit("not armed")

trig = eval_expr(f"(() => {{ SteamClient.URL.ExecuteSteamURL('steam://run/{APP_ID}'); return 'ExecuteSteamURL'; }})()")
print("trigger=", trig)

deadline = time.time() + 60
while time.time() < deadline:
    pend = eval_expr("window.__ftGameRoute.pending()")
    log = eval_expr("(window.__ftGameRoute.dump()||[]).slice(-15).map(e=>e.event)")
    print("tick pending=", pend, "events=", log)
    if pend:
        break
    time.sleep(0.5)
else:
    print("TIMEOUT after trigger")
    raise SystemExit(1)

print("pick=", json.dumps(eval_expr("window.__ftGameRoute.pick('tovakai')", timeout=30), indent=2))

deadline = time.time() + 30
while time.time() < deadline:
    events = eval_expr("(window.__ftGameRoute.dump()||[]).slice(-25).map(e=>e.event)")
    print("post events=", events)
    if "restore_scheduled" in (events or []) or "bypass_consumed" in (events or []):
        break
    time.sleep(0.5)

print(json.dumps(eval_expr("(window.__ftGameRoute.dump()||[]).slice(-30)"), indent=2)[:7000])
sock.close()
PY
EOF

echo
echo "=== wait for ft-game-run log ==="
ssh -o BatchMode=yes "$FRAME_HOST" 'for i in $(seq 1 30); do
  if [ -f /tmp/frametop-game-run.log ] && grep -q "DISPLAY=:2" /tmp/frametop-game-run.log 2>/dev/null; then
    echo "ok at ${i}s"; tail -2 /tmp/frametop-game-run.log; exit 0
  fi
  sleep 1
done; echo "TIMEOUT waiting for wrap log"; exit 1'

echo
echo "=== verify ==="
bash "$ROOT/test/_verify_tovakai_launch.sh"
bash "$ROOT/test/_probe_tovakai_hades_env.sh"
