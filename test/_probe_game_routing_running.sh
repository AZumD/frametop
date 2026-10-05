#!/usr/bin/env bash
# While game running: deeper SteamClient.Apps queries for active action / running state.
set -u
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
set +e
python3 - <<'PY'
import json, os, struct, base64, socket, urllib.request, time

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
expr = r"""
(async () => {
  const Apps = SteamClient.Apps;
  const appId = 1145360;
  const out = { appId };
  try { out.active = await Apps.GetActiveGameActions(); } catch(e){ out.activeErr=String(e); }
  try { out.forApp = await Apps.GetGameActionForApp(String(appId)); } catch(e){ out.forAppErr=String(e); }
  try {
    const cached = await Apps.GetCachedAppDetails?.(appId);
    out.cachedStatus = cached && {
      eDisplayStatus: cached.eDisplayStatus,
      strDisplayName: cached.strDisplayName,
      nPlaytimeForever: cached.nPlaytimeForever,
    };
  } catch(e){ out.cachedErr=String(e); }
  // live details
  try {
    out.detailsStatus = await new Promise((resolve, reject) => {
      let done=false;
      const t=setTimeout(()=>{ if(!done){done=true; reject(new Error('timeout'));}}, 2500);
      const u = Apps.RegisterForAppDetails(appId, (d) => {
        if(done) return; done=true; clearTimeout(t);
        try{ u?.unregister?.() ?? u?.(); }catch{}
        resolve({ eDisplayStatus: d.eDisplayStatus, strDisplayName: d.strDisplayName });
      });
    });
  } catch(e){ out.detailsStatusErr=String(e); }
  try { out.probeLog = window.__ftGameRouteProbe?.dump?.() || null; } catch(e){}
  // OpenVR overlay keys mentioning desktopgame
  try {
    const ov = SteamClient.OpenVR;
    out.hasOpenVR = !!ov;
  } catch(e){}
  return out;
})()
"""
res = ask("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True}, timeout=15)
val = res.get("result", {}).get("result", {})
if isinstance(val, dict) and val.get("type")=="object" and "value" in val:
    val = val["value"]
print(json.dumps(val, indent=2)[:12000])
open("/tmp/frametop-game-running-apps.json","w").write(json.dumps(val, indent=2))
sock.close()
PY
EOF
