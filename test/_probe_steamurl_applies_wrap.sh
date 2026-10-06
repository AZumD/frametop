#!/usr/bin/env bash
# Prove whether steam://run applies SetAppLaunchOptions wraps (Phase 5 used UI Play).
set -euo pipefail
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
APP_ID=${1:-1145360}
WRAP=/home/steamos/dev/frametop/session/ft-game-run

ssh -o BatchMode=yes "$FRAME_HOST" bash -s -- "$APP_ID" "$WRAP" <<'EOF'
set -euo pipefail
APP_ID=$1
WRAP=$2
pkill -f Hades.exe 2>/dev/null || true
sleep 2
rm -f /tmp/frametop-game-run.log
python3 - "$APP_ID" "$WRAP" <<'PY'
import json, os, struct, base64, socket, urllib.request, time, sys
APP_ID=int(sys.argv[1]); WRAP=sys.argv[2]

def http_json(url):
    return json.loads(urllib.request.urlopen(url, timeout=3).read())

def connect():
    shared=next(t for t in http_json("http://127.0.0.1:8080/json/list") if (t.get("title") or "")=="SharedJSContext")
    ws_url=shared["webSocketDebuggerUrl"]
    hostport,path=ws_url[5:].split("/",1); host,port=hostport.split(":"); port=int(port); path="/"+path
    key=base64.b64encode(os.urandom(16)).decode()
    req=(f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode()
    sock=socket.create_connection((host,port),timeout=5); sock.sendall(req); buf=b""
    while b"\r\n\r\n" not in buf: buf+=sock.recv(4096)
    header,rest=buf.split(b"\r\n\r\n",1)
    return sock, rest

def recv_frame(sock, leftover=b""):
    data=leftover
    while len(data)<2: data+=sock.recv(4096)
    b1,b2=data[0],data[1]; ln=b2&0x7f; idx=2
    if ln==126:
        while len(data)<idx+2: data+=sock.recv(4096)
        ln=struct.unpack("!H",data[idx:idx+2])[0]; idx+=2
    elif ln==127:
        while len(data)<idx+8: data+=sock.recv(4096)
        ln=struct.unpack("!Q",data[idx:idx+8])[0]; idx+=8
    while len(data)<idx+ln: data+=sock.recv(max(4096,ln))
    return b1&0x0f, data[idx:idx+ln], data[idx+ln:]

def send_text(sock, s):
    payload=s.encode(); header=bytearray([0x81]); n=len(payload); mask_bit=0x80
    if n<126: header.append(mask_bit|n)
    elif n<65536: header.append(mask_bit|126); header+=struct.pack("!H",n)
    else: header.append(mask_bit|127); header+=struct.pack("!Q",n)
    mask=os.urandom(4); header+=mask
    sock.sendall(bytes(header)+bytes(b^mask[i%4] for i,b in enumerate(payload)))

sock, leftover = connect(); mid=0

def ask(method, params=None, timeout=20):
    global mid, leftover
    mid+=1; msg={"id":mid,"method":method}
    if params is not None: msg["params"]=params
    send_text(sock, json.dumps(msg)); deadline=time.time()+timeout
    while time.time()<deadline:
        opcode,payload,leftover=recv_frame(sock, leftover)
        if opcode!=1: continue
        data=json.loads(payload)
        if data.get("id")==mid: return data
    raise TimeoutError(method)

def eval_expr(expr, timeout=20):
    res=ask("Runtime.evaluate",{"expression":expr,"returnByValue":True,"awaitPromise":True},timeout=timeout)
    if res.get("result",{}).get("exceptionDetails"):
        return {"__exception": res["result"]["exceptionDetails"]}
    val=res.get("result",{}).get("result",{})
    if isinstance(val, dict) and val.get("type")=="object" and "value" in val: val=val["value"]
    elif isinstance(val, dict) and val.get("type") in ("string","number","boolean") and "value" in val: val=val["value"]
    return val

ask("Runtime.enable")
# Disarm chooser so it cannot cancel.
print("disarm=", eval_expr("(()=>{ try{ window.__ftGameRoute?.dispose?.(); }catch(e){} return !window.__ftGameRoute; })()"))

wrapped = WRAP + " %command%"
set_expr = f"""
(async () => {{
  await SteamClient.Apps.SetAppLaunchOptions({APP_ID}, {json.dumps(wrapped)});
  const live = await new Promise((resolve, reject) => {{
    let done=false;
    const t=setTimeout(()=>{{ if(!done){{done=true; reject(new Error('timeout'));}}}}, 4000);
    const u = SteamClient.Apps.RegisterForAppDetails({APP_ID}, (d) => {{
      if(done) return; done=true; clearTimeout(t);
      try {{ u?.unregister?.() ?? u?.(); }} catch {{}}
      resolve(d.strLaunchOptions||'');
    }});
  }});
  return live;
}})()
"""
live = eval_expr(set_expr, timeout=15)
print("live_options=", live)
time.sleep(1.0)
trig = eval_expr(f"(() => {{ SteamClient.URL.ExecuteSteamURL('steam://run/{APP_ID}'); return 'ok'; }})()")
print("trigger=", trig)
sock.close()
print("waiting 8s for process…")
time.sleep(8)
PY
echo "=== log ==="
tail -20 /tmp/frametop-game-run.log 2>/dev/null || echo no_log
echo "=== cmdline ==="
pgrep -af 'Hades|ft-game-run|reaper.*1145360' 2>/dev/null | grep -v pgrep | head -8
echo "=== restore options to empty ==="
python3 - "$APP_ID" <<'PY'
import json,os,struct,base64,socket,urllib.request,time,sys
APP_ID=int(sys.argv[1])
def http_json(url):
    return json.loads(urllib.request.urlopen(url, timeout=3).read())
shared=next(t for t in http_json("http://127.0.0.1:8080/json/list") if (t.get("title") or "")=="SharedJSContext")
ws_url=shared["webSocketDebuggerUrl"]
hostport,path=ws_url[5:].split("/",1); host,port=hostport.split(":"); port=int(port); path="/"+path
key=base64.b64encode(os.urandom(16)).decode()
req=(f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode()
sock=socket.create_connection((host,port),timeout=5); sock.sendall(req); buf=b""
while b"\r\n\r\n" not in buf: buf+=sock.recv(4096)
header,rest=buf.split(b"\r\n\r\n",1)
def recv_frame(leftover=b""):
    data=leftover
    while len(data)<2: data+=sock.recv(4096)
    b1,b2=data[0],data[1]; ln=b2&0x7f; idx=2
    if ln==126:
        while len(data)<idx+2: data+=sock.recv(4096)
        ln=struct.unpack("!H",data[idx:idx+2])[0]; idx+=2
    elif ln==127:
        while len(data)<idx+8: data+=sock.recv(4096)
        ln=struct.unpack("!Q",data[idx:idx+8])[0]; idx+=8
    while len(data)<idx+ln: data+=sock.recv(max(4096,ln))
    return b1&0x0f, data[idx:idx+ln], data[idx+ln:]
def send_text(s):
    payload=s.encode(); header=bytearray([0x81]); n=len(payload); mask_bit=0x80
    if n<126: header.append(mask_bit|n)
    elif n<65536: header.append(mask_bit|126); header+=struct.pack("!H",n)
    else: header.append(mask_bit|127); header+=struct.pack("!Q",n)
    mask=os.urandom(4); header+=mask
    sock.sendall(bytes(header)+bytes(b^mask[i%4] for i,b in enumerate(payload)))
leftover=rest; mid=0
def ask(method, params=None, timeout=15):
    global mid, leftover
    mid+=1; msg={"id":mid,"method":method}
    if params is not None: msg["params"]=params
    send_text(json.dumps(msg)); deadline=time.time()+timeout
    while time.time()<deadline:
        opcode,payload,leftover=recv_frame(leftover)
        if opcode!=1: continue
        data=json.loads(payload)
        if data.get("id")==mid: return data
    raise TimeoutError(method)
ask("Runtime.enable")
ask("Runtime.evaluate",{"expression":f"(async()=>{{await SteamClient.Apps.SetAppLaunchOptions({APP_ID},''); return 'restored';}})()","returnByValue":True,"awaitPromise":True})
print("restored")
sock.close()
PY
EOF
