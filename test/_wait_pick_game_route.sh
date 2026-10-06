#!/usr/bin/env bash
# Wait for a pending game-route chooser (after user hits Play), then pick a route.
set -euo pipefail
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
ROUTE=${1:-tovakai}
TIMEOUT=${2:-90}
if [[ "$ROUTE" != steamvr && "$ROUTE" != tovakai && "$ROUTE" != cancel ]]; then
  echo "usage: $0 steamvr|tovakai|cancel [timeout_sec]" >&2
  exit 2
fi
echo "Waiting up to ${TIMEOUT}s for pending chooser, then pick=$ROUTE"
echo "(Press Play on Hades in SteamVR now.)"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s -- "$ROUTE" "$TIMEOUT" <<'EOF'
set -euo pipefail
ROUTE=$1
TIMEOUT=$2
python3 - "$ROUTE" "$TIMEOUT" <<'PY'
import json, os, struct, base64, socket, urllib.request, time, sys
ROUTE = sys.argv[1]
TIMEOUT = int(sys.argv[2])

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

def ask(method, params=None, timeout=12):
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

def eval_expr(expr, timeout=12):
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
armed = eval_expr("!!window.__ftGameRoute")
print("armed=", armed)
if not armed:
    print("FAIL: not armed — run _arm_game_route_chooser.sh")
    sys.exit(1)

deadline = time.time() + TIMEOUT
status_expr = "(() => { const p=window.__ftGameRoute; if(!p) return {ok:false}; const log=p.dump?.()||[]; const last=log.slice(-8); const pend=p.pending?.()||null; return {ok:true, hasPick:typeof p.pick==='function', pending:pend, last}; })()"
saw_pending = False
while time.time() < deadline:
    st = eval_expr(status_expr)
    last = (st or {}).get("last") or []
    events = [e.get("event") for e in last if isinstance(e, dict)]
    pend = (st or {}).get("pending")
    if pend or ("popup" in events) or ("classified" in events) or ("cancelled" in events and "classified" in events):
        saw_pending = True
        print("pending seen:", events, "pending=", pend)
        break
    # Progress heartbeat every ~5s
    if int(time.time()) % 5 == 0:
        print("waiting… events=", events)
    time.sleep(0.75)
else:
    print("TIMEOUT waiting for pending chooser. last=", json.dumps(eval_expr(status_expr), indent=2))
    sys.exit(1)

# Ensure pending exists (classified may race slightly ahead of pending assign)
for _ in range(20):
    pend = eval_expr("window.__ftGameRoute?.pending?.() || null")
    if pend:
        break
    time.sleep(0.2)

pick_expr = f"(() => {{ const p=window.__ftGameRoute; p.pick({json.dumps(ROUTE)}); return {{ok:true, route:{json.dumps(ROUTE)}, log:(p.dump?.()||[]).slice(-12)}}; }})()"
time.sleep(0.3)
result = eval_expr(pick_expr, timeout=20)
print(json.dumps(result, indent=2))
# Wait for wrap/relaunch (Tovakai waitWrapped can take a few seconds).
want = ("wrap_ok", "relaunch", "awaiting_play", "wrap_verify_fail", "finish_err", "bypass_consumed")
done_deadline = time.time() + 25
while time.time() < done_deadline:
    final = eval_expr("(() => ({ok:!!window.__ftGameRoute, log:(window.__ftGameRoute?.dump?.()||[]).slice(-20)}))()")
    events = [e.get("event") for e in (final.get("log") or []) if isinstance(e, dict)]
    if any(e in want for e in events[-12:]):
        print("--- after ---")
        print(json.dumps(final, indent=2))
        break
    time.sleep(0.5)
else:
    final = eval_expr("(() => ({ok:!!window.__ftGameRoute, log:(window.__ftGameRoute?.dump?.()||[]).slice(-20)}))()")
    print("--- after (timeout waiting wrap/relaunch) ---")
    print(json.dumps(final, indent=2))
sock.close()
PY
EOF
