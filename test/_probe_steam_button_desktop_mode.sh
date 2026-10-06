#!/usr/bin/env bash
# Arm logging for SystemKeyEvents + OpenVR button presses (observe Steam button).
# Does not synthesize presses. User should press Steam button once, then dump.
set -u
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
MODE=${1:-arm} # arm | dump | dispose
ssh -o BatchMode=yes "$FRAME_HOST" bash -s -- "$MODE" <<'EOF'
set -euo pipefail
MODE=$1
python3 - "$MODE" <<'PY'
import json, os, struct, base64, socket, urllib.request, time, sys
MODE = sys.argv[1]

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
if MODE == "dump":
    expr = "(() => { const p=window.__ftSteamBtnProbe; if(!p) return {ok:false,error:'not_armed'}; return {ok:true, log:p.dump(), dash: (SteamClient.OpenVR?.VROverlay?.IsDashboardVisible?.() ?? null)}; })()"
elif MODE == "dispose":
    expr = "(() => { try { window.__ftSteamBtnProbe?.dispose?.(); } catch(e){} return {ok:true, disposed:true}; })()"
else:
    expr = r"""
(() => {
  const G = window;
  if (G.__ftSteamBtnProbe?.dispose) try { G.__ftSteamBtnProbe.dispose(); } catch {}
  const log = [];
  const push = (row) => { row.t = Date.now(); log.push(row); if (log.length > 100) log.shift(); console.info('ft-steam-btn', JSON.stringify(row)); };
  const unsubs = [];
  const wrapUnsub = (u) => { unsubs.push(u); return u; };
  try {
    wrapUnsub(SteamClient.System.UI.RegisterForSystemKeyEvents((...args) => {
      push({ event: 'SystemKey', args: args.map(a => (a && typeof a === 'object') ? JSON.parse(JSON.stringify(a)) : a) });
      try { push({ event: 'dashAfterSystemKey', dash: SteamClient.OpenVR.VROverlay.IsDashboardVisible() }); } catch(e) {}
    }));
  } catch (e) { push({ event: 'SystemKey_err', err: String(e) }); }
  try {
    wrapUnsub(SteamClient.OpenVR.RegisterForButtonPress((...args) => {
      push({ event: 'OpenVRButton', args: args.map(a => (a && typeof a === 'object') ? JSON.parse(JSON.stringify(a)) : a) });
    }));
  } catch (e) { push({ event: 'OpenVRButton_err', err: String(e) }); }
  try {
    wrapUnsub(SteamClient.OpenVR.VROverlay.RegisterForButtonPress((...args) => {
      push({ event: 'VROverlayButton', args: args.map(a => (a && typeof a === 'object') ? JSON.parse(JSON.stringify(a)) : a) });
    }));
  } catch (e) { push({ event: 'VROverlayButton_err', err: String(e) }); }
  try {
    wrapUnsub(SteamClient.OpenVR.VROverlay.RegisterForVisibilityChanged?.((...args) => {
      push({ event: 'OverlayVisibility', args: args.map(a => (a && typeof a === 'object') ? JSON.parse(JSON.stringify(a)) : a) });
    }));
  } catch (e) {}
  G.__ftSteamBtnProbe = {
    dump: () => log.slice(),
    dispose: () => {
      for (const u of unsubs) {
        try { u?.unregister?.() ?? u?.(); } catch {}
      }
      delete G.__ftSteamBtnProbe;
    },
  };
  push({ event: 'armed' });
  return { ok: true, mode: 'observe-steam-button' };
})()
"""
res = ask("Runtime.evaluate", {"expression": expr, "returnByValue": True})
val = res.get("result", {}).get("result", {})
if isinstance(val, dict) and val.get("type")=="object" and "value" in val:
    val = val["value"]
print(json.dumps(val, indent=2)[:12000])
sock.close()
if MODE == "arm":
    print("Armed. Press the physical Steam/System button once (game→desktop transition), then: bash test/_probe_steam_button_desktop_mode.sh dump")
PY
EOF
