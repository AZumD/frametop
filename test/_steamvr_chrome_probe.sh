#!/bin/bash
# Read-only SteamVR floating-panel chrome visual probe on Frame host.
set -u

echo "===== PATHS ====="
for p in \
  /opt/steamvr \
  /opt/steamvr/resources \
  /opt/steamvr/resources/webinterface \
  /opt/steamvr/resources/webinterface/dashboard \
  /opt/steamvr/resources/webinterface/dashboard/css \
  /opt/steamvr/resources/webinterface/dashboard/images \
  /opt/steamvr/content/vrmonitor \
  /opt/steamvr/content/vrmonitor/stylesheets \
  /opt/steamvr/content/vrmonitor/textures \
  /opt/steamvr/content/vrmonitor/icons \
  /home/steamos/steamvr \
  /home/steamos/.local/share/Steam \
  /home/steamos/.steam/steam
do
  if [ -e "$p" ]; then
    echo "EXISTS $p"
    if [ -d "$p" ]; then
      echo "  entries: $(ls -1 "$p" 2>/dev/null | wc -l)"
    fi
  else
    echo "MISSING $p"
  fi
done

echo
echo "===== FILENAME SEARCH resize/drag/grab/title/chrome/handle/corner/window ====="
find /opt/steamvr /home/steamos/steamvr \
  \( -iname '*resize*' -o -iname '*drag*' -o -iname '*grab*' -o -iname '*titlebar*' \
     -o -iname '*title_bar*' -o -iname '*chrome*' -o -iname '*handle*' \
     -o -iname '*corner*' -o -iname '*windowframe*' -o -iname '*window_frame*' \
     -o -iname '*desktopgame*' -o -iname '*float*' \) 2>/dev/null \
  | grep -viE 'float_depth|mvfloat|hallucination_float|float\.fxo|float\.spv|hand_right_close' \
  | head -120

echo
echo "===== vrmonitor stylesheets / textures ====="
ls -la /opt/steamvr/content/vrmonitor/stylesheets 2>/dev/null || true
ls -la /opt/steamvr/content/vrmonitor/textures 2>/dev/null | head -80 || true
find /opt/steamvr/content/vrmonitor -type f \( -name '*.css' -o -name '*.qss' -o -name '*.svg' -o -name '*.png' \) 2>/dev/null \
  | grep -iE 'resize|drag|grab|title|chrome|handle|corner|window|bar|button|close|frame' \
  | head -80

echo
echo "===== CSS: border-radius / rgba / hover counts ====="
for f in /opt/steamvr/resources/webinterface/dashboard/css/*.css \
         /opt/steamvr/resources/webinterface/shared/css/*.css \
         /opt/steamvr/content/vrmonitor/stylesheets/*; do
  [ -f "$f" ] || continue
  br=$(grep -o 'border-radius:[^;]*' "$f" 2>/dev/null | sort | uniq -c | sort -rn | head -8)
  if [ -n "$br" ]; then
    echo "-- $f radii --"
    echo "$br"
  fi
done

echo
echo "===== steamvr.css CSS variables ====="
grep -oE -- '--[a-zA-Z0-9_-]+:[^;}]+' /opt/steamvr/resources/webinterface/shared/css/steamvr.css 2>/dev/null | head -100

echo
echo "===== systemui.css color / radius extracts ====="
python3 - <<'PY'
import re, pathlib
p = pathlib.Path('/opt/steamvr/resources/webinterface/dashboard/css/systemui.css')
t = p.read_text(errors='ignore')
radii = sorted(set(re.findall(r'border-radius:\s*([^;]+)', t)))
rgbas = sorted(set(re.findall(r'rgba?\([^)]+\)', t)))
hexes = sorted(set(re.findall(r'#[0-9a-fA-F]{3,8}\b', t)))
hovers = re.findall(r'[^{}]*:hover[^{]*\{[^}]+\}', t)
print('radii:', radii)
print('rgba count', len(rgbas))
for x in rgbas[:40]:
    print(' ', x)
print('hex count', len(hexes))
for x in hexes[:40]:
    print(' ', x)
print('hover rules', len(hovers))
for h in hovers[:20]:
    print(' ', h[:200].replace('\n',' '))
PY

echo
echo "===== chunk CSS: search chrome-ish class names ====="
python3 - <<'PY'
import re, pathlib
root = pathlib.Path('/opt/steamvr/resources/webinterface/dashboard/css')
keys = re.compile(r'(resize|drag|grab|titlebar|title_bar|windowchrome|corner|handle|toolbar|caption|chrome)', re.I)
for f in sorted(root.glob('*.css')):
    t = f.read_text(errors='ignore')
    hits = sorted(set(m.group(0) for m in keys.finditer(t)))
    if hits:
        print(f'{f.name}: keywords {hits}')
    # extract nearby class fragments
    for m in re.finditer(r'.{0,30}(resize|dragBar|drag_bar|titleBar|grabBar|WindowChrome|cornerHandle|Caption).{0,30}', t, re.I):
        print(' ', f.name, '::', m.group(0)[:120])
PY

echo
echo "===== JS non-chunk search ====="
python3 - <<'PY'
import re, pathlib
root = pathlib.Path('/opt/steamvr/resources/webinterface/dashboard')
keys = re.compile(r'(resizeHandle|dragBar|titleBar|grabBar|WindowChrome|cornerRadius|CornerRadius|overlayChrome|DesktopGame|floatWindow)', re.I)
for f in sorted(root.glob('*.js')):
    if f.name.startswith('chunk') or 'libraries' in str(f):
        continue
    t = f.read_text(errors='ignore')
    ms = list(keys.finditer(t))
    if ms:
        print(f'{f.name}: {len(ms)} hits')
        for m in ms[:15]:
            i=m.start(); print(' ', t[max(0,i-40):i+60].replace('\n',' '))
# sample chunks lightly
for f in sorted((root).glob('chunk*.js'))[:12]:
    t = f.read_text(errors='ignore')
    ms = list(keys.finditer(t))
    if ms:
        print(f'{f.name}: {len(ms)} hits')
        for m in ms[:10]:
            i=m.start(); print(' ', t[max(0,i-40):i+60].replace('\n',' '))
PY

echo
echo "===== binary strings (arm64) ====="
for b in vrdashboard vrcompositor vrmonitor vrserver; do
  f=/opt/steamvr/bin/linuxarm64/$b
  [ -f "$f" ] || continue
  echo "-- $b --"
  strings "$f" 2>/dev/null | grep -iE 'resize|dragbar|titlebar|windowchrome|cornerradius|grabbar|overlaychrome|desktopgame|handlecorner|window.?control' | sort -u | head -50
done

echo
echo "===== dashboard images icons list ====="
ls /opt/steamvr/resources/webinterface/dashboard/images/icons/ 2>/dev/null | head -120

echo
echo "===== SVG geometry samples (bindingui + svr icons) ====="
python3 - <<'PY'
import pathlib, re
paths = list(pathlib.Path('/opt/steamvr/resources/webinterface/dashboard/images').rglob('*.svg'))
print('svg count', len(paths))
# pick close/settings/desktop/more/keyboard icons
prefer = ['close','settings','desktop','more','keyboard','menu','power','volume','eye','recenter']
picked=[]
for p in paths:
    n=p.name.lower()
    if any(k in n for k in prefer):
        picked.append(p)
for p in picked[:25]:
    t=p.read_text(errors='ignore')
    vb=re.search(r'viewBox="([^"]+)"', t)
    fills=sorted(set(re.findall(r'fill="([^"]+)"', t)))
    strokes=sorted(set(re.findall(r'stroke="([^"]+)"', t)))
    print(f'{p.relative_to("/opt/steamvr/resources/webinterface/dashboard/images")}: vb={vb.group(1) if vb else None} fills={fills[:6]} strokes={strokes[:6]} size={len(t)}')
PY

echo
echo "===== home steamvr tree ====="
find /home/steamos/steamvr -maxdepth 3 -type d 2>/dev/null | head -60
find /home/steamos/steamvr -iname '*resize*' -o -iname '*chrome*' -o -iname '*drag*' 2>/dev/null | head -40

echo
echo "===== screenshot / capture constraints notes ====="
# Look for settings about screenshots / capture
strings /opt/steamvr/bin/linuxarm64/vrdashboard 2>/dev/null | grep -iE 'screenshot|capture|drm|protected|hdcp|overlay.*alpha' | sort -u | head -40
grep -iE 'screenshot|capture' /opt/steamvr/resources/settingsschema.vrsettings 2>/dev/null | head -40

echo
echo "===== DONE ====="
