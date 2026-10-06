#!/usr/bin/env bash
# Probe which APIs can relaunch an app using launch options (not bare RunGame).
set -euo pipefail
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
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
    while len(data) < 2: data += sock.recv(4096)
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
expr = r"""
(() => {
  const SC = window.SteamClient || {};
  const has = (path) => {
    let o = SC;
    for (const p of path.split('.')) {
      if (o == null || !(p in o)) return {ok:false, type:'missing'};
      o = o[p];
    }
    return {ok:true, type: typeof o};
  };
  const keys = (obj) => Object.keys(obj||{}).sort();
  return {
    Apps: keys(SC.Apps).filter(k => /Run|Launch|Start|Game|URL|Navigate|Open|Execute/i.test(k)),
    Browser: keys(SC.Browser),
    System: keys(SC.System).filter(k => /URL|Open|Navigate|Execute|Run/i.test(k)),
    URL: keys(SC.URL),
    Window: keys(SC.Window).filter(k => /URL|Navigate|Open/i.test(k)),
    samples: {
      'Apps.RunGame': has('Apps.RunGame'),
      'Apps.RunGameEx': has('Apps.RunGameEx'),
      'Apps.LaunchApp': has('Apps.LaunchApp'),
      'Apps.ContinueGameAction': has('Apps.ContinueGameAction'),
      'Browser.OpenURL': has('Browser.OpenURL'),
      'Browser.OpenSteamURL': has('Browser.OpenSteamURL'),
      'System.OpenInSystemBrowser': has('System.OpenInSystemBrowser'),
      'URL.ExecuteSteamURL': has('URL.ExecuteSteamURL'),
      'URL.Navigate': has('URL.Navigate'),
    }
  };
})()
"""
res = ask("Runtime.evaluate", {"expression": expr, "returnByValue": True})
val = res.get("result", {}).get("result", {})
if isinstance(val, dict) and "value" in val:
    val = val["value"]
print(json.dumps(val, indent=2))
sock.close()
PY
EOF
