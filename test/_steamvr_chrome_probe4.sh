#!/bin/bash
# GrabHandle visuals + color tokens + screenshot constraints.
set -u
python3 - <<'PY'
import re, pathlib, subprocess

js = pathlib.Path('/opt/steamvr/resources/webinterface/dashboard/chunk~8012d0c89.js').read_text(errors='ignore')

# GrabHandle region
idx = js.find('debug_name:"GrabHandle"')
print('===== GrabHandle REGION =====')
print(js[idx-800:idx+1200])

# Search CSS for GrabHandle / grabhandle / StatusBar / ControlBarTrayBackground
css_files = list(pathlib.Path('/opt/steamvr/resources/webinterface/dashboard/css').glob('*.css'))
print('\n===== CSS Grab/StatusBar/Tray =====')
for f in css_files:
    t = f.read_text(errors='ignore')
    for key in ['GrabHandle','grabhandle','StatusBar','ControlBarTray','FrameGrab','DragBar','grab-bar','GrabBar']:
        if key.lower() in t.lower() or key in t:
            print(f.name, 'has', key)
    rules = re.findall(r'[^{}]*(?:StatusBar|ControlBarTray|GrabHandle|grabhandle|FrameGrab)[^{]*\{[^}]*\}', t, re.I)
    for r in rules[:30]:
        print(f.name, '::', r[:350])
        print('---')

# Color vars from CSS
print('\n===== COLOR / SIZE TOKENS =====')
for name in ['chunk~93a8598f9.css','chunk~b48d3fba7.css','chunk~66c0d1388.css','systemui.css']:
    t = (pathlib.Path('/opt/steamvr/resources/webinterface/dashboard/css')/name).read_text(errors='ignore')
    # extract :root-ish blocks with gamepadui
    for m in re.finditer(r'--gamepadui-[a-zA-Z0-9_-]+\s*:\s*[^;}{]+', t):
        pass
    vars_ = sorted(set(re.findall(r'--(?:gamepadui|dashboard|settings|control-bar|resize)[a-zA-Z0-9_-]*\s*:\s*[^;}{]+', t)))
    print('FILE', name, len(vars_))
    for v in vars_[:120]:
        print(' ', v)

# shared steamvr.css full palette
print('\n===== steamvr.css full vars =====')
t = pathlib.Path('/opt/steamvr/resources/webinterface/shared/css/steamvr.css').read_text(errors='ignore')
for v in re.findall(r'--[a-zA-Z0-9_-]+\s*:\s*[^;}{]+', t):
    print(' ', v)

# showResizeHandle logic
for f in [pathlib.Path('/opt/steamvr/resources/webinterface/dashboard/systemui.js'),
          pathlib.Path('/opt/steamvr/resources/webinterface/dashboard/chunk~2e670652e.js')]:
    t = f.read_text(errors='ignore')
    idx = t.find('showResizeHandle')
    if idx>=0:
        print('\n===== showResizeHandle in', f.name, '=====')
        print(t[idx-200:idx+500])

# meters_per_pixel constant
for m in re.finditer(r'meters_per_pixel|m_fVRGamepadUI_MetersPerPixel|iZ\s*=\s*[0-9.]+', js):
    pass
# find export iZ
for m in re.finditer(r'iZ[=:]\s*([0-9.eE+-]+)', js):
    print('iZ', m.group(0))
for m in re.finditer(r'MetersPerPixel[=:]\s*([0-9.eE+-]+)', js):
    print(m.group(0))

# Search for opacity props on GrabHandle / ResizeHandle components
for key in ['opacity', 'tint', 'scale', 'width:.66675', 'BottomCenter', 'BottomRight']:
    if key in js:
        print('has', key)

# Extract GrabHandle component function more carefully via regex
m = re.search(r'function\s+\w*\([^)]*\)\{[^}]*GrabHandle[\s\S]{0,1500}', js)
# fallback: find className near GrabHandle
idx = js.find('GrabHandle')
# find preceding function with className for grab UI
# Look for SVG or div content inside GrabHandle Zkm
region = js[idx:idx+1500]
print('\n===== GrabHandle AFTER =====')
print(region)

# Look backward for component definition that renders into GrabHandle
# Search "grab" classnames in css modules exports near Grab
for m in re.finditer(r'exports=\{[^}]{0,400}Grab[^}]{0,400}\}', js):
    print('EXPORT', m.group(0)[:400])

# Binary scenegraph
print('\n===== compositor scenegraph strings =====')
out = subprocess.getoutput("strings /opt/steamvr/bin/linuxarm64/vrcompositor | grep -E 'resize-handle|frame-resize|GrabHandle|grab-handle|StatusBar|only_visible'")
print(out)

# Screenshot / capture settings
print('\n===== settingsschema related =====')
schema = pathlib.Path('/opt/steamvr/resources/settingsschema.vrsettings').read_text(errors='ignore')
# print nearby keys
keys = re.findall(r'"[^"]*(?:screen|capture|mirror|protect|hdcp|camera|dashboard)[^"]*"\s*:\s*\{[^}]{0,200}\}', schema, re.I)
for k in keys[:40]:
    print(k[:250])
    print('---')

# Also check if Steam UI has protected content flags in dashboard
out = subprocess.getoutput("strings /opt/steamvr/bin/linuxarm64/vrdashboard | grep -iE 'screenshot|capture|protected|HDCP|DRM' | sort -u | head -40")
print('DASHBOARD CAPTURE STRINGS:')
print(out)

# pin SVG + desktopgame svg
print('\n===== SVGs =====')
for p in [
 '/opt/steamvr/content/vrmonitor/icons/icon_vrwindow_pin.svg',
 '/opt/steamvr/resources/icon_steamvr_desktopgame.svg',
]:
    print('FILE', p)
    print(pathlib.Path(p).read_text(errors='ignore'))

# PNG dimensions via python struct
import struct
def png_size(path):
    with open(path,'rb') as f:
        sig=f.read(8)
        if sig[:4]!=b'\x89PNG': return None
        length=struct.unpack('>I', f.read(4))[0]
        ctype=f.read(4)
        data=f.read(length)
        w,h=struct.unpack('>II', data[:8])
        return w,h
icon_dir=pathlib.Path('/opt/steamvr/content/vrmonitor/icons')
for p in sorted(icon_dir.glob('icon_vrwindow*')) + sorted(icon_dir.glob('icon_headsetview_window*')) + sorted(icon_dir.glob('icon_headsetview_widget_close*')):
    if p.suffix=='.png':
        print(p.name, png_size(p), 'bytes', p.stat().st_size)

# dashboard close icons
dicons=pathlib.Path('/opt/steamvr/resources/webinterface/dashboard/images/icons')
for p in sorted(dicons.glob('icon_close*')):
    if p.suffix=='.png':
        print('dashboard', p.name, png_size(p))

# Control bar button size vars from CSS usage (values may be in JS theme)
print('\n===== search JS for dashboard-control-bar / gamepadui color assignments =====')
for f in sorted(pathlib.Path('/opt/steamvr/resources/webinterface/dashboard').glob('chunk*.js')):
    t=f.read_text(errors='ignore')
    if 'gamepadui-darkest-grey' in t or 'dashboard-control-bar-height' in t or '--gamepadui' in t:
        print('HIT', f.name)
        for m in re.finditer(r'(gamepadui-[a-z0-9-]+|dashboard-control-bar-[a-z0-9-]+|dashboard-minitoggle-[a-z0-9-]+|settings-border-radius|1a9fff|88ccf1)[^,]{0,40}', t, re.I):
            pass
        # extract theme object-ish
        for m in re.finditer(r'--gamepadui-[a-zA-Z0-9_-]+\s*:\s*[^;\"\']+', t):
            print(' ', m.group(0)[:120])
        for m in re.finditer(r'--dashboard-[a-zA-Z0-9_-]+\s*:\s*[^;\"\']+', t):
            print(' ', m.group(0)[:120])
        for m in re.finditer(r'dashboard-control-bar-[a-zA-Z0-9_-]+["\']?\s*[:=]\s*["\']?[^,\"\']+', t):
            print(' ', m.group(0)[:120])
PY
