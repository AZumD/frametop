#!/usr/bin/env bash
# Dump steamFrame.uiPatches from Frame nix-config + find LaunchNonSteam wrap source.
set -u
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
set +e
echo "=== home.nix steamFrame block ==="
python3 - <<'PY'
from pathlib import Path
text = Path("/home/steamos/nix-config/home.nix").read_text()
# print from steamFrame = { ... matching braces roughly
idx = text.find("steamFrame")
print(text[idx:idx+3500] if idx>=0 else "no steamFrame")
PY
echo
echo "=== find LaunchNonSteam wrap in nix store ==="
rg -l --no-heading 'LaunchNonSteamApp' /nix/store/*-patch.js /nix/store/*steam-frame* 2>/dev/null | head -20
rg -n --no-heading -C2 'LaunchNonSteamApp' /nix/store/*-patch.js 2>/dev/null | head -80
echo
echo "=== injector / ui patches services ==="
systemctl --user list-units --all 2>/dev/null | grep -iE 'ui-patch|sfui|steamui|webhelper-debugger' | head
ls /nix/store/*steam-ui-patches* 2>/dev/null | head
pgrep -af 'injector|steam-ui-patches|sfui' | head
echo
echo "=== GetLaunchOptionsForApp / RegisterForAppDetails shapes ==="
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
def ask(method, params=None, timeout=8):
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
# Install observe-only GameActionStart logger (no Cancel). Returns handle.
expr = r"""
(() => {
  const G = window;
  if (G.__ftGameRouteProbe?.dispose) { try { G.__ftGameRouteProbe.dispose(); } catch {} }
  const log = [];
  const Apps = SteamClient.Apps;
  const unsub = Apps.RegisterForGameActionStart((gameActionId, gameId, action, launchSource) => {
    const row = {
      t: Date.now(),
      gameActionId, gameId: String(gameId), action, launchSource,
    };
    try {
      const n = Number(BigInt(gameId) & 0xffffffffn);
      row.appIdGuess = n;
    } catch (e) { row.appIdGuessErr = String(e); }
    try {
      const d = Apps.GetGameActionDetails?.(gameActionId);
      row.details = d;
    } catch (e) { row.detailsErr = String(e); }
    try {
      const active = Apps.GetActiveGameActions?.();
      row.active = active;
    } catch (e) { row.activeErr = String(e); }
    log.push(row);
    if (log.length > 50) log.shift();
    console.info('ft-game-route-probe', JSON.stringify(row));
  });
  // Also end events
  let unsubEnd = null;
  try {
    unsubEnd = Apps.RegisterForGameActionEnd((gameActionId) => {
      const row = { t: Date.now(), end: true, gameActionId };
      log.push(row);
      console.info('ft-game-route-probe-end', JSON.stringify(row));
    });
  } catch (e) {}
  G.__ftGameRouteProbe = {
    version: 1,
    mode: 'observe-only',
    log,
    dump: () => log.slice(),
    dispose: () => { try { unsub?.unregister?.() ?? unsub?.(); } catch {} try { unsubEnd?.unregister?.() ?? unsubEnd?.(); } catch {} delete G.__ftGameRouteProbe; },
  };
  // Probe launch options API shape for Hades if installed
  const out = { installed: true, probe: 'observe-only RegisterForGameActionStart v1' };
  try {
    const lo = Apps.GetLaunchOptionsForApp;
    out.GetLaunchOptionsForApp = typeof lo;
  } catch (e) {}
  return out;
})()
"""
res = ask("Runtime.evaluate", {"expression": expr, "returnByValue": True})
val = res.get("result", {}).get("result", {})
if isinstance(val, dict) and val.get("type")=="object" and "value" in val:
    val = val["value"]
print("install:", json.dumps(val, indent=2))

# Probe GetLaunchOptionsForApp + RegisterForAppDetails for Hades (1145360)
expr2 = r"""
(async () => {
  const Apps = SteamClient.Apps;
  const appId = 1145360; // Hades
  const out = { appId };
  try {
    const opts = await Apps.GetLaunchOptionsForApp(appId);
    out.launchOptions = opts;
  } catch (e) { out.launchOptionsErr = String(e); }
  try {
    // RegisterForAppDetails often returns unsubscribe + pushes callback
    out.details = await new Promise((resolve, reject) => {
      let done = false;
      const t = setTimeout(() => { if (!done) { done=true; reject(new Error('timeout')); } }, 3000);
      try {
        const u = Apps.RegisterForAppDetails(appId, (d) => {
          if (done) return; done=true; clearTimeout(t);
          try { u?.unregister?.() ?? u?.(); } catch {}
          resolve(d);
        });
      } catch (e) { done=true; clearTimeout(t); reject(e); }
    });
    // slim fields of interest
    const d = out.details || {};
    out.detailsSlim = {
      keys: Object.keys(d||{}).slice(0,80),
      nAppID: d.nAppID ?? d.appid ?? d.unAppID,
      strDisplayName: d.strDisplayName ?? d.name,
      rtLastPlayed: d.rtLastPlayed,
      bIsApplication: d.bIsApplication,
      // VR-ish
      vr_supported: d.vr_supported ?? d.bVRSupported ?? d.vrSupported,
      vr_only: d.vr_only ?? d.bVROnly ?? d.vrOnly,
      openvr: d.openvr, openxr: d.openxr,
      strLaunchOptions: d.strLaunchOptions ?? d.launch_options,
      vecLaunch: d.vecLaunch ?? d.launchConfigurations ?? d.rgLaunchOptions,
    };
  } catch (e) { out.detailsErr = String(e); }
  // RunGame length via Function.length
  try { out.RunGameArity = Apps.RunGame.length; } catch {}
  try { out.CancelGameActionArity = Apps.CancelGameAction.length; } catch {}
  try { out.SetAppLaunchOptionsArity = Apps.SetAppLaunchOptions.length; } catch {}
  try { out.RegisterForGameActionStartArity = Apps.RegisterForGameActionStart.length; } catch {}
  return out;
})()
"""
res2 = ask("Runtime.evaluate", {"expression": expr2, "returnByValue": True, "awaitPromise": True}, timeout=12)
val2 = res2.get("result", {}).get("result", {})
if isinstance(val2, dict) and val2.get("type")=="object" and "value" in val2:
    val2 = val2["value"]
print("hades meta:", json.dumps(val2, indent=2)[:10000])
open("/tmp/frametop-hades-meta.json","w").write(json.dumps(val2, indent=2))
sock.close()
print("observe probe armed: window.__ftGameRouteProbe — launch a 2D game then dump log")
PY
EOF
