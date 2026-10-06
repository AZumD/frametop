#!/bin/bash
# Deeper extraction of Frame SteamVR panel chrome CSS (resize/grab/frame controls).
set -u

python3 - <<'PY'
import re, pathlib

files = [
    pathlib.Path('/opt/steamvr/resources/webinterface/dashboard/css/chunk~93a8598f9.css'),
    pathlib.Path('/opt/steamvr/resources/webinterface/dashboard/css/controllerbindingui.css'),
    pathlib.Path('/opt/steamvr/resources/webinterface/dashboard/css/debugcommands.css'),
    pathlib.Path('/opt/steamvr/resources/webinterface/dashboard/css/settings_desktop.css'),
    pathlib.Path('/opt/steamvr/resources/webinterface/dashboard/css/chunk~66c0d1388.css'),
    pathlib.Path('/opt/steamvr/resources/webinterface/dashboard/css/chunk~b48d3fba7.css'),
    pathlib.Path('/opt/steamvr/resources/webinterface/shared/css/steamvr.css'),
    pathlib.Path('/opt/steamvr/content/vrmonitor/stylesheets/vrmonitor_common.qss'),
]

patterns = [
    r'frameresizehandle_[^{]+\{[^}]+\}',
    r'framegrab[^{]*\{[^}]+\}',
    r'framecontrols[^{]*\{[^}]+\}',
    r'legacydashboardframecontrols_[^{]+\{[^}]+\}',
    r'DashboardMain[^{]*\{[^}]+\}',
    r'ControlBar[^{]*\{[^}]+\}',
    r'TitleBar[^{]*\{[^}]+\}',
    r'GrabBar[^{]*\{[^}]+\}',
    r'grabbar[^{]*\{[^}]+\}',
    r'FrameControls[^{]*\{[^}]+\}',
]

# Also dump CSS custom properties related to resize/settings
var_re = re.compile(r'--[a-zA-Z0-9_-]*(resize|handle|settings|button|radius|spacing|control|track|corner)[a-zA-Z0-9_-]*\s*:\s*[^;]+', re.I)

for f in files:
    if not f.exists():
        print('MISSING', f)
        continue
    t = f.read_text(errors='ignore')
    print('\n########', f, 'len', len(t))
    # find all class prefixes mentioning frame/resize/grab/controlbar
    prefixes = sorted(set(re.findall(r'\.([a-zA-Z0-9_-]*(?:resize|grab|framecontrol|ControlBar|TitleBar|caption|chrome|Handle)[a-zA-Z0-9_-]*)', t, re.I)))
    print('class-like hits:', prefixes[:80])
    vars_found = sorted(set(var_re.findall(t)))
    # var_re.findall with groups returns only groups; fix:
    vars_found = sorted(set(m.group(0) for m in re.finditer(r'--[a-zA-Z0-9_-]*(?:resize|handle|settings|button|radius|spacing|control|track|corner)[a-zA-Z0-9_-]*\s*:\s*[^;}{]+', t, re.I)))
    print('vars:')
    for v in vars_found[:80]:
        print(' ', v)
    for pat in patterns:
        ms = re.findall(pat, t, re.I)
        if ms:
            print(f'-- pattern {pat} ({len(ms)}) --')
            for m in ms[:40]:
                print(m[:400])
                print('---')

# Extract continuous block around frameresizehandle from chunk~93
for name in ['chunk~93a8598f9.css', 'controllerbindingui.css']:
    p = pathlib.Path('/opt/steamvr/resources/webinterface/dashboard/css') / name
    t = p.read_text(errors='ignore')
    for key in ['frameresizehandle', 'framegrab', 'FrameGrab', 'grabhandle', 'GrabHandle', 'legacydashboardframecontrols', 'dashboardframe', 'ControlBar', 'TitleBar']:
        idx = t.lower().find(key.lower())
        if idx < 0:
            continue
        # expand to cover a large contiguous region of related rules
        start = max(0, idx - 200)
        # walk forward collecting related rules while key-ish tokens continue
        end = min(len(t), idx + 4000)
        chunk = t[start:end]
        print(f'\n===== REGION {name} around {key} =====')
        print(chunk)
        print('===== END REGION =====')

# SVG for resize if embedded as data or separate
print('\n===== search SVG path stroke for resize icons in JS =====')
root = pathlib.Path('/opt/steamvr/resources/webinterface/dashboard')
for f in list(root.glob('*.js')) + list(root.glob('chunk*.js')):
    t = f.read_text(errors='ignore')
    if 'frameresizehandle' in t or 'ResizeCorner' in t or 'ResizeSVG' in t:
        print('HIT', f.name)
        for m in re.finditer(r'.{0,80}(frameresizehandle|ResizeCorner|ResizeSVG|ResizeHandle).{0,120}', t):
            print(m.group(0).replace('\n',' ')[:220])
        # look for path d= near Resize
        for m in re.finditer(r'ResizeSVG[\s\S]{0,800}', t):
            print('SVGCTX', m.group(0)[:800].replace('\n',' '))
            break

# icon_vrwindow sizes
print('\n===== vrwindow icon file sizes / identify =====')
import os, subprocess
icon_dir = pathlib.Path('/opt/steamvr/content/vrmonitor/icons')
for p in sorted(icon_dir.glob('icon_vrwindow*')) + sorted(icon_dir.glob('icon_headsetview*')) + sorted(icon_dir.glob('*slider*')):
    print(f'{p.name}\t{p.stat().st_size}')

# try identify or file
for p in [
    icon_dir/'icon_vrwindow_close.png',
    icon_dir/'icon_vrwindow_close_hover.png',
    icon_dir/'icon_vrwindow_minimize.png',
    icon_dir/'icon_vrwindow_pin.png',
    icon_dir/'icon_vrwindow_pin.svg',
    icon_dir/'icon_vrwindow_pinned16.svg',
]:
    if p.exists():
        out = subprocess.getoutput(f'file {p}')
        print(out)
        if p.suffix == '.svg':
            print(p.read_text(errors='ignore')[:500])

# QSS window chrome bits
print('\n===== vrmonitor_common.qss window/title/button extracts =====')
qss = pathlib.Path('/opt/steamvr/content/vrmonitor/stylesheets/vrmonitor_common.qss').read_text(errors='ignore')
for key in ['Title', 'title', 'Close', 'close', 'Pin', 'pin', 'Minimize', 'resize', 'Handle', 'Frame', 'Button', 'hover', 'border-radius', 'background']:
    pass
# extract rules containing TitleBar/Close/Pin/VRWindow
for m in re.finditer(r'[^{}\n]*?(?:Title|Close|Pin|Minimize|VRWindow|Window|Handle|Caption)[^{]*\{[^}]+\}', qss, re.I):
    print(m.group(0)[:350])
    print('---')

# color tokens in qss
print('QSS colors:')
for c in sorted(set(re.findall(r'#[0-9A-Fa-f]{3,8}', qss)))[:60]:
    print(' ', c)
print('QSS rgba:')
for c in sorted(set(re.findall(r'rgba?\([^)]+\)', qss)))[:40]:
    print(' ', c)

print('\n===== gamepadui / settings CSS vars from chunks =====')
for name in ['chunk~93a8598f9.css','chunk~b48d3fba7.css','chunk~66c0d1388.css']:
    t = (pathlib.Path('/opt/steamvr/resources/webinterface/dashboard/css')/name).read_text(errors='ignore')
    # root :root or html vars
    for m in re.finditer(r'(?::root|html|:host|\.DashboardMain|\.SettingsMain)[^{]*\{([^}]{0,4000})\}', t):
        block = m.group(0)
        if '--' in block:
            print('BLOCK in', name)
            print(block[:2500])
            print('---')
PY
