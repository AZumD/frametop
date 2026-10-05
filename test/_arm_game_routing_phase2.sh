#!/usr/bin/env bash
# Phase 2: temporary CDP inject — CancelGameAction on LaunchApp for one appId,
# then stock RunGame once with a one-shot bypass. No Tovakai wrap. No launch-option mutation.
set -u
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
APP_ID="${1:-1145360}"  # default Hades
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s -- "$APP_ID" <<'EOF'
set -euo pipefail
APP_ID=$1
python3 - "$APP_ID" <<'PY'
import json, os, struct, base64, socket, urllib.request, time, sys

APP_ID = int(sys.argv[1])

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
def ask(method, params=None, timeout=10):
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

# Inject Phase 2 handler. Uses only Cancel + RunGame; no SetAppLaunchOptions.
expr = r"""
(() => {
  const APP = %d;
  const G = window;
  if (G.__ftGameRouteP2?.dispose) { try { G.__ftGameRouteP2.dispose(); } catch {} }
  if (G.__ftGameRouteProbe?.dispose) { try { G.__ftGameRouteProbe.dispose(); } catch {} }

  const Apps = SteamClient.Apps;
  const log = [];
  const push = (row) => {
    row.t = Date.now();
    log.push(row);
    if (log.length > 80) log.shift();
    console.info('ft-game-route-p2', JSON.stringify(row));
  };

  // gameIds that should skip intercept exactly once (our own RunGame).
  const bypass = new Set();
  let pending = false;

  const appIdOf = (gameId) => {
    try { return Number(BigInt(gameId) & 0xffffffffn); } catch { return Number(gameId) || 0; }
  };

  const unsubStart = Apps.RegisterForGameActionStart((gameActionId, gameId, action, launchSource) => {
    const idStr = String(gameId);
    const appId = appIdOf(gameId);
    const row = { event: 'start', gameActionId, gameId: idStr, appId, action, launchSource, pending, bypass: bypass.has(idStr) };
    push(row);

    if (action !== 'LaunchApp') return;
    if (appId !== APP) { push({ event: 'ignore_other_app', appId }); return; }

    if (bypass.has(idStr) || bypass.has(String(APP))) {
      bypass.delete(idStr);
      bypass.delete(String(APP));
      push({ event: 'bypass_consumed', gameActionId, gameId: idStr });
      return;
    }

    if (pending) {
      push({ event: 'ignore_while_pending', gameActionId });
      try { Apps.CancelGameAction(gameActionId); } catch (e) { push({ event: 'cancel_pending_err', err: String(e) }); }
      return;
    }

    pending = true;
    let cancelOk = false, cancelErr = null;
    try {
      Apps.CancelGameAction(gameActionId);
      cancelOk = true;
    } catch (e) {
      cancelErr = String(e);
    }
    push({ event: 'cancel', gameActionId, cancelOk, cancelErr });

    // Relaunch stock after a short delay (community pattern ~500ms).
    const relaunchGameId = idStr; // Phase1 showed plain appId string works as gameId
    const launchSourceArg = (typeof launchSource === 'number') ? launchSource : 100;
    setTimeout(() => {
      bypass.add(relaunchGameId);
      bypass.add(String(APP));
      push({ event: 'relaunch_begin', gameId: relaunchGameId, launchSourceArg, bypassSize: bypass.size });
      let runResult = null, runErr = null;
      try {
        // Community: RunGame(gameId, "", -1, 100)
        runResult = Apps.RunGame(relaunchGameId, '', -1, launchSourceArg);
      } catch (e) {
        runErr = String(e);
      }
      push({ event: 'relaunch_called', runResult: runResult === undefined ? 'undefined' : runResult, runErr });
      // Clear pending after calling; bypass covers the resulting Start.
      pending = false;
      // Safety: expire bypass if Start never arrives
      setTimeout(() => {
        if (bypass.has(relaunchGameId) || bypass.has(String(APP))) {
          bypass.delete(relaunchGameId);
          bypass.delete(String(APP));
          push({ event: 'bypass_expired' });
        }
      }, 15000);
    }, 500);
  });

  const unsubEnd = Apps.RegisterForGameActionEnd((gameActionId) => {
    push({ event: 'end', gameActionId });
  });

  let unsubTask = null;
  try {
    unsubTask = Apps.RegisterForGameActionTaskChange((gameActionId, appId, taskName, details) => {
      push({ event: 'task', gameActionId, appId, taskName, details: details == null ? null : String(details).slice(0, 200) });
    });
  } catch (e) {
    push({ event: 'task_sub_err', err: String(e) });
  }

  G.__ftGameRouteP2 = {
    version: 2,
    mode: 'cancel-relaunch-stock',
    appId: APP,
    log,
    dump: () => log.slice(),
    pending: () => pending,
    bypass: () => [...bypass],
    dispose: () => {
      try { unsubStart?.unregister?.() ?? unsubStart?.(); } catch {}
      try { unsubEnd?.unregister?.() ?? unsubEnd?.(); } catch {}
      try { unsubTask?.unregister?.() ?? unsubTask?.(); } catch {}
      delete G.__ftGameRouteP2;
    },
  };
  return { ok: true, mode: 'cancel-relaunch-stock', appId: APP, version: 2 };
})()
""" % APP_ID

res = ask("Runtime.evaluate", {"expression": expr, "returnByValue": True})
val = res.get("result", {}).get("result", {})
if isinstance(val, dict) and val.get("type") == "object" and "value" in val:
    val = val["value"]
print(json.dumps(val, indent=2))
open("/tmp/frametop-game-route-p2-armed.json", "w").write(json.dumps(val, indent=2))
sock.close()
print(f"armed Phase2 for appId={APP_ID}. Quit the game if running, then launch it once from SteamVR.")
PY
EOF
