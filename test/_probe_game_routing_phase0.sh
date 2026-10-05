#!/usr/bin/env bash
# Phase 0 live inspect: nested Plasma env + Steam UI patch surface on the Frame.
set -u
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
set +e
echo "=== steam-frame-nix / nix presence ==="
ls -la ~/.local/state/steam-frame-nix 2>/dev/null | head || echo "(no state dir)"
ls /nix/store 2>/dev/null | head -3 || echo no_nix_store
command -v steam-frame-nix-cleanup || echo "steam-frame-nix-cleanup not on PATH"
ls ~/dev 2>/dev/null
echo
echo "=== asterism / steamui on frame ==="
ls -la ~/dev/Asterism 2>/dev/null | head || echo "(no ~/dev/Asterism)"
systemctl --user list-units --all 2>/dev/null | grep -iE 'steamui|asterism|steam-frame|webhelper|debugger' | head
echo
echo "=== plasmashell.env candidates ==="
rt=/run/user/$(id -u)
for f in "$rt/plasmashell.env" "$rt/frametop/plasmashell.env" "$rt/frametop/"*/plasmashell.env; do
  [ -f "$f" ] || continue
  echo "FOUND $f"
  tr '\0' '\n' < "$f" | grep -E '^(WAYLAND_DISPLAY|DISPLAY|XDG_RUNTIME_DIR|DBUS_SESSION_BUS_ADDRESS|XDG_SESSION_TYPE)=' || true
done
echo
echo "=== nested runtime dir ==="
ls -la "$rt/frametop" 2>/dev/null | head -25 || echo "(no frametop runtime)"
echo
echo "=== frametop procs ==="
pgrep -af 'ft-screens|ft-launch|ft-taskbar|plasmashell|kwin' | head -20
echo
echo "=== steam / CDP ==="
pgrep -af 'steamwebhelper|chrome_crashpad|vrwebhelper' | head -15
ss -ltn 2>/dev/null | grep -E ':8080|:27060|:9222' || true
curl -sS --max-time 2 http://127.0.0.1:8080/json/list 2>/dev/null | python3 -c '
import json,sys
try:
  data=json.load(sys.stdin)
except Exception as e:
  print("cdp list fail", e); sys.exit(0)
for t in data:
  title=t.get("title") or ""
  url=t.get("url") or ""
  if "SharedJS" in title or "gamepadui" in title.lower() or "steam" in title.lower():
    print(f"- title={title!r} type={t.get(\"type\")} url={url[:80]}")
' || echo "(no CDP on :8080)"
echo
echo "=== sample installed apps ==="
ls ~/.steam/steam/steamapps/common 2>/dev/null | head -40 || ls ~/.local/share/Steam/steamapps/common 2>/dev/null | head -40
echo
echo "=== home-manager / uiPatches remnants ==="
find ~/.config ~/.local/state /etc -maxdepth 3 \( -iname '*steam-frame*' -o -iname '*uiPatches*' -o -iname '*steamFrame*' \) 2>/dev/null | head -40
EOF
