#!/usr/bin/env bash
# Phase 0c: steam-frame-nix config on Frame + CDP Apps probe via stdlib HTTP upgrade or node.
set -u
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
set +e
echo "=== nix-config steamFrame ==="
ls -la ~/nix-config 2>/dev/null | head
rg -n --no-heading -i 'uiPatches|LaunchNonSteam|steamFrame|patches' ~/nix-config 2>/dev/null | head -60
echo
echo "=== patch.js samples in nix store (steam-frame) ==="
for f in /nix/store/bpsfji81whg71l1i0gygvhg4x97zfsw9-patch.js \
         /nix/store/*-patch.js; do
  [ -f "$f" ] || continue
  case "$f" in *node_modules*) continue ;; esac
  echo "---- $f ----"
  head -80 "$f"
  echo
done 2>/dev/null | head -200
echo
echo "=== ui-patches json ==="
for f in ~/.local/state/steam-frame-nix/ui-patches/*.json; do
  echo "---- $f ----"; cat "$f"; echo
done
echo
echo "=== CDP Apps probe with python stdlib websocket ==="
python3 - <<'PY'
import json, os, ssl, struct, hashlib, base64, socket, urllib.request, time

def http_json(url):
    return json.loads(urllib.request.urlopen(url, timeout=3).read())

targets = http_json("http://127.0.0.1:8080/json/list")
shared = next((t for t in targets if (t.get("title") or "") == "SharedJSContext"), None)
if not shared:
    shared = next((t for t in targets if "SharedJS" in (t.get("title") or "")), None)
if not shared:
    print("NO SharedJS"); raise SystemExit(1)
ws_url = shared["webSocketDebuggerUrl"]
# ws://host:port/path
assert ws_url.startswith("ws://")
hostport, path = ws_url[5:].split("/", 1)
host, port = hostport.split(":")
port = int(port)
path = "/" + path
key = base64.b64encode(os.urandom(16)).decode()
req = (
    f"GET {path} HTTP/1.1\r\n"
    f"Host: {host}:{port}\r\n"
    f"Upgrade: websocket\r\n"
    f"Connection: Upgrade\r\n"
    f"Sec-WebSocket-Key: {key}\r\n"
    f"Sec-WebSocket-Version: 13\r\n\r\n"
).encode()
sock = socket.create_connection((host, port), timeout=5)
sock.sendall(req)
# read headers
buf = b""
while b"\r\n\r\n" not in buf:
    chunk = sock.recv(4096)
    if not chunk:
        break
    buf += chunk
header, rest = buf.split(b"\r\n\r\n", 1)
if b"101" not in header.split(b"\r\n", 1)[0]:
    print("upgrade failed", header[:200]); raise SystemExit(1)

def recv_frame(leftover=b""):
    data = leftover
    while len(data) < 2:
        data += sock.recv(4096)
    b1, b2 = data[0], data[1]
    masked = b2 & 0x80
    ln = b2 & 0x7f
    idx = 2
    if ln == 126:
        while len(data) < idx + 2:
            data += sock.recv(4096)
        ln = struct.unpack("!H", data[idx:idx+2])[0]
        idx += 2
    elif ln == 127:
        while len(data) < idx + 8:
            data += sock.recv(4096)
        ln = struct.unpack("!Q", data[idx:idx+8])[0]
        idx += 8
    if masked:
        while len(data) < idx + 4:
            data += sock.recv(4096)
        mask = data[idx:idx+4]
        idx += 4
    else:
        mask = None
    while len(data) < idx + ln:
        data += sock.recv(max(4096, ln))
    payload = data[idx:idx+ln]
    leftover = data[idx+ln:]
    if mask:
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    opcode = b1 & 0x0f
    return opcode, payload, leftover

def send_text(s):
    payload = s.encode()
    header = bytearray([0x81])
    n = len(payload)
    mask_bit = 0x80  # client must mask
    if n < 126:
        header.append(mask_bit | n)
    elif n < 65536:
        header.append(mask_bit | 126)
        header += struct.pack("!H", n)
    else:
        header.append(mask_bit | 127)
        header += struct.pack("!Q", n)
    mask = os.urandom(4)
    header += mask
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    sock.sendall(bytes(header) + masked)

leftover = rest
mid = 0

def ask(method, params=None, timeout=8):
    global mid, leftover
    mid += 1
    msg = {"id": mid, "method": method}
    if params is not None:
        msg["params"] = params
    send_text(json.dumps(msg))
    deadline = time.time() + timeout
    while time.time() < deadline:
        opcode, payload, leftover = recv_frame(leftover)
        if opcode != 1:
            continue
        data = json.loads(payload)
        if data.get("id") == mid:
            return data
    raise TimeoutError(method)

ask("Runtime.enable")
expr = r"""
(() => {
  const out = { hasSteamClient: typeof SteamClient !== 'undefined' };
  if (!out.hasSteamClient) return out;
  const Apps = SteamClient.Apps || null;
  out.hasApps = !!Apps;
  if (!Apps) return out;
  out.appsKeys = Object.keys(Apps).sort();
  const want = [
    'RegisterForGameActionStart','CancelGameAction','RunGame','SetAppLaunchOptions',
    'RegisterForAppDetails','GetAppData','GetAppDetails','LaunchNonSteamApp',
    'RegisterForGameActionTaskChange','RegisterForGameActionUserResponse',
    'GetGameActionForApp','GetLaunchQueryParams','AddLaunchOption','SetAppLaunchOptions',
    'GetShortcutDataByID','GetAllShortcuts','PromptToChangeShortcut','TerminateApp'
  ];
  out.presence = {};
  for (const k of want) out.presence[k] = typeof Apps[k];
  // also fuzzy match
  out.fuzzy = out.appsKeys.filter(k => /GameAction|Launch|RunGame|LaunchOption|Compat|VR/i.test(k));
  try { out.RunGameStr = String(Apps.RunGame); } catch(e){ out.RunGameStr=String(e);}
  try { out.CancelGameActionStr = String(Apps.CancelGameAction);} catch(e){ out.CancelGameActionStr=String(e);}
  try { out.RegisterForGameActionStartStr = String(Apps.RegisterForGameActionStart);} catch(e){ out.RegisterForGameActionStartStr=String(e);}
  try { out.SetAppLaunchOptionsStr = String(Apps.SetAppLaunchOptions);} catch(e){ out.SetAppLaunchOptionsStr=String(e);}
  try { out.LaunchNonSteamAppStr = String(Apps.LaunchNonSteamApp);} catch(e){ out.LaunchNonSteamAppStr=String(e);}
  return out;
})()
"""
res = ask("Runtime.evaluate", {"expression": expr, "returnByValue": True})
val = res.get("result", {}).get("result", {})
if val.get("type") == "object" and "value" in val:
    val = val["value"]
print(json.dumps(val, indent=2)[:12000])
open("/tmp/frametop-steam-apps-api.json","w").write(json.dumps(val, indent=2))
sock.close()
print("wrote /tmp/frametop-steam-apps-api.json")
PY
EOF
