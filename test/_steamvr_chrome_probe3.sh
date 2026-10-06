#!/bin/bash
# Exact extraction of Frame resize handle CSS + SVG path + grab/move chrome.
set -u

python3 - <<'PY'
import re, pathlib, json

css = pathlib.Path('/opt/steamvr/resources/webinterface/dashboard/css/chunk~93a8598f9.css').read_text(errors='ignore')

# Pull the full frameresizehandle rule set by finding all rules whose selector contains frameresizehandle
rules = re.findall(r'[^{}]*frameresizehandle[^{]*\{[^}]*\}', css)
print('===== ALL frameresizehandle RULES =====')
for r in rules:
    print(r)
    print('---')

# Also grab CSS vars declared on ResizeHandleButton
m = re.search(r'\.frameresizehandle_ResizeHandleButton_3BhgE\{[^}]+\}', css)
print('BUTTON ROOT:', m.group(0) if m else None)

# From JS module 7785 / resize component
js = pathlib.Path('/opt/steamvr/resources/webinterface/dashboard/chunk~8012d0c89.js').read_text(errors='ignore')

# Extract SVG path template around cornerRadius
for m in re.finditer(r'cornerRadius[\s\S]{0,500}', js):
    s = m.group(0)
    if 'M 34' in s or 'Resize' in s or 'path' in s:
        print('===== cornerRadius CTX =====')
        print(s[:500])

# Better: find the template literal with M 34
idx = js.find('M 34 4')
if idx >= 0:
    print('===== SVG PATH TEMPLATE =====')
    print(js[idx-200:idx+400])

# Find ResizeHandle overlay creation flags
for key in ['ResizeHandle', 'only_visible_with_laser', 'hide_lasermouse', 'frame-resize', 'GrabHandle', 'MoveHandle', 'DragBar', 'drag_bar', 'grab_bar', 'FrameGrab', 'title_bar', 'TitleBarOverlay']:
    if key.lower() in js.lower() or key in js:
        print(f'KEY {key} present')

# Extract scene-graph / overlay creation near ResizeHandle
idx = js.find('debug_name:"ResizeHandle"')
if idx < 0:
    idx = js.find("debug_name:'ResizeHandle'")
if idx >= 0:
    print('===== ResizeHandle overlay config =====')
    print(js[idx-500:idx+800])

# Search all dashboard JS for grab/move bar related debug names
root = pathlib.Path('/opt/steamvr/resources/webinterface/dashboard')
for f in sorted(root.glob('*.js')) + sorted(root.glob('chunk*.js')):
    t = f.read_text(errors='ignore')
    for m in re.finditer(r'debug_name:"([^"]+)"', t):
        name = m.group(1)
        if re.search(r'resize|grab|drag|move|title|chrome|frame|bar|handle|control', name, re.I):
            print(f'{f.name}: debug_name={name}')
            print(' ', t[max(0,m.start()-180):m.start()+220].replace('\n',' ')[:300])

# Extract CSS variables for dashboard control bar / settings from chunk
print('\n===== DASHBOARD / SETTINGS CSS VARS =====')
for name in ['chunk~93a8598f9.css','chunk~b48d3fba7.css','chunk~66c0d1388.css']:
    t = (pathlib.Path('/opt/steamvr/resources/webinterface/dashboard/css')/name).read_text(errors='ignore')
    vars_ = sorted(set(re.findall(r'--(?:dashboard|settings|gamepadui|control|resize|handle)[a-zA-Z0-9_-]*\s*:\s*[^;}{]+', t)))
    print(name, 'count', len(vars_))
    for v in vars_:
        print(' ', v)

# Frame controls idle opacity etc already known; get full legacy frame controls CSS
print('\n===== LEGACY FRAME CONTROLS FULL =====')
for name in ['chunk~93a8598f9.css','debugcommands.css','settings_desktop.css']:
    t = (pathlib.Path('/opt/steamvr/resources/webinterface/dashboard/css')/name).read_text(errors='ignore')
    rules = re.findall(r'[^{}]*legacydashboardframecontrols[^{]*\{[^}]*\}', t)
    if rules:
        print('FILE', name, len(rules))
        for r in rules:
            print(r)
            print('---')

# Binary strings for scenegraph resize handle params
import subprocess
print('\n===== vrcompositor resize-handle related strings =====')
out = subprocess.getoutput("strings /opt/steamvr/bin/linuxarm64/vrcompositor | grep -iE 'resize-handle|frame-resize|CSGResize|GrabHandle|drag-bar|title-bar|window-chrome|corner-radius|only_visible_with_laser|laser'")
print('\n'.join(sorted(set(out.splitlines()))[:80]))

print('\n===== vrdashboard strings chrome =====')
out = subprocess.getoutput("strings /opt/steamvr/bin/linuxarm64/vrdashboard | grep -iE 'resize-handle|frame-resize|GrabHandle|drag|title-bar|FrameControls|cornerRadius|desktopgame'")
print('\n'.join(sorted(set(out.splitlines()))[:80]))

# Pin SVG geometry
print('\n===== pin SVG =====')
for p in [
    pathlib.Path('/opt/steamvr/content/vrmonitor/icons/icon_vrwindow_pin.svg'),
    pathlib.Path('/opt/steamvr/content/vrmonitor/icons/icon_vrwindow_pinned16.svg'),
    pathlib.Path('/opt/steamvr/resources/icon_steamvr_desktopgame.svg'),
]:
    if p.exists():
        print('FILE', p)
        print(p.read_text(errors='ignore')[:800])

# Sample dashboard icon SVGs geometry
print('\n===== dashboard icon SVG samples =====')
idir = pathlib.Path('/opt/steamvr/resources/webinterface/dashboard/images/icons')
for name in ['svr_desktop.svg','svr_settings.svg','svr_more.svg','svr_keyboard.svg','svr_menu.svg','svr_power.svg','icon_close.png']:
    p = idir/name
    if not p.exists():
        # try find
        hits = list(idir.glob(name.replace('.svg','*')))
        print('missing', name, 'alts', [h.name for h in hits[:5]])
        continue
    if p.suffix == '.svg':
        t = p.read_text(errors='ignore')
        print(name, 'len', len(t))
        print(t[:400])
        print('---')

# Screenshot constraints from settings schema
print('\n===== settings schema screenshot/capture =====')
schema = pathlib.Path('/opt/steamvr/resources/settingsschema.vrsettings').read_text(errors='ignore')
for line in schema.splitlines():
    if re.search(r'screen|capture|mirror|protect|hdcp|camera', line, re.I):
        print(line[:240])

# Check Steam client for VR floating window chrome (gamescope / steam overlay)
print('\n===== Steam local UI paths =====')
for base in [
    pathlib.Path('/home/steamos/.local/share/Steam'),
    pathlib.Path('/home/steamos/.steam/steam'),
]:
    # look for steamui / steamvr resources
    for sub in ['steamui', 'steamvr', 'tenfoot', 'controller_base']:
        p = base/sub
        if p.exists():
            print('EXISTS', p)
    hits = list(base.glob('**/steamvr*/**/*resize*'))[:20]
    print(base, 'resize hits', hits)

# Also search in Steam for desktopgame textures
import os
for base in [pathlib.Path('/home/steamos/.local/share/Steam')]:
    cmd = f"find {base} -iname '*desktopgame*' -o -iname '*vrwindow*' -o -iname '*resizehandle*' 2>/dev/null | head -40"
    print(subprocess.getoutput(cmd))
PY
