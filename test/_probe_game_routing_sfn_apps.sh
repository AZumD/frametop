#!/usr/bin/env bash
# Phase 0b: inspect steam-frame-nix ui-patches + SharedJS SteamClient.Apps surface (read-only).
set -u
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
set +e
echo "=== steam-frame-nix ui-patches ==="
ls -la ~/.local/state/steam-frame-nix/ui-patches/ 2>/dev/null
ls -la ~/.local/state/frametop/steam-frame-nix/ 2>/dev/null | head
find ~/.local/state/steam-frame-nix ~/.local/state/frametop/steam-frame-nix -type f 2>/dev/null | head -80
echo
echo "=== sample patch contents (names + LaunchNonSteam / GameAction hits) ==="
find ~/.local/state/steam-frame-nix ~/.local/state/frametop/steam-frame-nix /nix/store -name '*.js' 2>/dev/null | head -40
# Grep installed patch sources for launch hooks
rg -n --no-heading -i 'LaunchNonSteam|RegisterForGameAction|RunGame|SetAppLaunchOptions|uiPatches|steamFrame' \
  ~/.local/state/steam-frame-nix ~/.local/state/frametop/steam-frame-nix 2>/dev/null | head -40
# Also search nix store desktop-user.js if present
store_js=$(ls /nix/store/*steam-frame-nix-desktop-user.js 2>/dev/null | head -1)
if [ -n "$store_js" ]; then
  echo "STORE_JS=$store_js"
  rg -n --no-heading -i 'LaunchNonSteam|RegisterForGameAction|RunGame|patch' "$store_js" 2>/dev/null | head -40
  wc -c "$store_js"
fi
echo
echo "=== home-manager flake / config pointers ==="
ls -la ~/.config/home-manager 2>/dev/null | head
ls -la ~/src 2>/dev/null | head
find ~/src ~/.config -maxdepth 4 -iname '*steam*frame*' 2>/dev/null | head -40
echo
echo "=== CDP SharedJS + SteamClient.Apps probe (observe only) ==="
python3 - <<'PY'
import json, urllib.request, ssl
ctx = ssl._create_unverified_context()
try:
    raw = urllib.request.urlopen("http://127.0.0.1:8080/json/list", context=ctx, timeout=3).read()
    targets = json.loads(raw)
except Exception as e:
    print("cdp list fail", e)
    raise SystemExit(0)
shared = None
for t in targets:
    title = t.get("title") or ""
    url = t.get("url") or ""
    typ = t.get("type") or ""
    interesting = ("SharedJS" in title) or ("gamepadui" in title.lower()) or ("steamloopback" in url)
    if interesting:
        print(f"target title={title!r} type={typ} id={t.get('id')} url={url[:100]}")
    if title == "SharedJSContext" or ("SharedJS" in title and shared is None):
        shared = t
if not shared:
    print("NO SharedJSContext target")
    raise SystemExit(0)
ws_url = shared.get("webSocketDebuggerUrl")
print("using", shared.get("title"), ws_url)
try:
    import websocket  # type: ignore
except Exception:
    # stdlib-only fallback via websockets may not exist; try asyncio-less manual
    print("no websocket-client module; writing probe script for later")
    open("/tmp/frametop-game-routing-sharedjs.json","w").write(json.dumps(shared, indent=2))
    raise SystemExit(0)

import time
ws = websocket.create_connection(ws_url, timeout=5)
mid = 0

def ask(method, params=None, timeout=5):
    global mid
    mid += 1
    msg = {"id": mid, "method": method}
    if params is not None:
        msg["params"] = params
    ws.send(json.dumps(msg))
    deadline = time.time() + timeout
    while time.time() < deadline:
        raw = ws.recv()
        data = json.loads(raw)
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
  const names = Object.keys(Apps).sort();
  out.appsKeys = names;
  const want = [
    'RegisterForGameActionStart','CancelGameAction','RunGame','SetAppLaunchOptions',
    'RegisterForAppDetails','GetAppDetails','GetShortcutData','LaunchNonSteamApp',
    'RegisterForGameActionTaskChange','RegisterForGameActionUserResponse',
    'GetGameActionDetails','GetLaunchOptionsForApp','GetAppLaunchOptions'
  ];
  out.presence = {};
  for (const k of want) out.presence[k] = typeof Apps[k];
  // RunGame arity / toString
  try { out.RunGame = String(Apps.RunGame); } catch (e) { out.RunGame = String(e); }
  try { out.CancelGameAction = String(Apps.CancelGameAction); } catch (e) { out.CancelGameAction = String(e); }
  try { out.RegisterForGameActionStart = String(Apps.RegisterForGameActionStart); } catch (e) { out.RegisterForGameActionStart = String(e); }
  try { out.SetAppLaunchOptions = String(Apps.SetAppLaunchOptions); } catch (e) { out.SetAppLaunchOptions = String(e); }
  try { out.LaunchNonSteamApp = String(Apps.LaunchNonSteamApp); } catch (e) { out.LaunchNonSteamApp = String(e); }
  return out;
})()
"""
res = ask("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": False})
print(json.dumps(res.get("result", {}).get("result", res), indent=2)[:8000])
ws.close()
PY
EOF
