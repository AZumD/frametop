#!/usr/bin/env python3
"""Read-only probe of SteamVR ControlBar / systemui assets on the Frame."""
import re
import os

CSS = "/opt/steamvr/resources/webinterface/dashboard/css/chunk~93a8598f9.css"
CSS2 = "/opt/steamvr/resources/webinterface/dashboard/css/chunk~66c0d1388.css"
CSS3 = "/opt/steamvr/resources/webinterface/dashboard/css/chunk~b48d3fba7.css"
JS = "/opt/steamvr/resources/webinterface/dashboard/chunk~8012d0c89.js"
JS_MAIN = "/opt/steamvr/resources/webinterface/dashboard/systemui.js"
ICONS = "/opt/steamvr/resources/webinterface/dashboard/images/icons"

def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()

css = read(CSS) + read(CSS2) + read(CSS3)
js = read(JS)
js_main = read(JS_MAIN) if os.path.exists(JS_MAIN) else ""
alljs = js + "\n" + js_main

print("=== CSS VARS mentioning control-bar / gamepadui / dashboard-control ===")
vars_ = sorted(set(re.findall(
    r"--(?:dashboard-control-bar|control-bar|gamepadui|settings-control|settings-border|dashboard-status)[a-z0-9-]*",
    css + alljs,
)))
for v in vars_:
    print(v)

print("\n=== BLOCKS THAT DEFINE control-bar / gamepadui vars ===")
for m in re.finditer(r"[^{}]{0,300}\{[^}]{0,6000}\}", css):
    block = m.group(0)
    if "--dashboard-control-bar" in block or "--control-bar-" in block:
        if re.search(r"--[a-z0-9-]+:", block):
            print(block[:3000])
            print("---")

print("\n=== CORE ControlBar RULES ===")
parts = re.findall(r"[^{}]+\{[^{}]*\}", css)
for p in parts:
    sel = p.split("{", 1)[0]
    if re.search(
        r"\.ControlBar\b|\.MainControlBar|\.ControlBarButton|\.ControlBarGroup|"
        r"\.ControlBarTray|\.ControlBarSlider|\.ControlBarButtonTooltip|"
        r"\.ControlBarSpacing|ControlBarTrayAnimation",
        sel,
    ):
        print(p.strip())
        print("---")

print("\n=== HOVER / BLOOM RELATED (ControlBarButton before/after/filter/box-shadow) ===")
for p in parts:
    if "ControlBarButton" in p and any(x in p for x in ["hover", "before", "after", "box-shadow", "filter", "bloom", "gradient"]):
        print(p.strip())
        print("---")

print("\n=== COMPONENT NAME TOKENS IN JS ===")
for pat in [
    r"ControlBar[A-Za-z0-9_]*",
    r"MainControlBar",
    r"allowLegacyControlBar",
    r"StatusBar",
    r"PowerMenu[A-Za-z0-9_]*",
    r"NowPlaying",
    r"DashboardMain",
]:
    found = sorted(set(re.findall(pat, alljs)))
    print(pat, "=>", found)

print("\n=== className string literals containing ControlBar ===")
for m in sorted(set(re.findall(r'className:"([^"]*ControlBar[^"]*)"', alljs))):
    print(m)
for m in sorted(set(re.findall(r'"((?:Main)?ControlBar[A-Za-z0-9_]*)"', alljs))):
    print("str", m)

print("\n=== IMAGE PATH LITERALS ===")
imgs = sorted(set(re.findall(r"/dashboard/images/[A-Za-z0-9_./-]+", alljs)))
for i in imgs:
    print(i)

print("\n=== ICON FILENAME LITERALS (svr_/icon_) ===")
svgs = sorted(set(re.findall(
    r"(?:[A-Za-z0-9_/.-]*)(?:svr_[A-Za-z0-9_]+\.svg|icon_[A-Za-z0-9_]+\.(?:png|svg))",
    alljs,
)))
for i in svgs:
    print(i)

print("\n=== EXISTENCE CHECKS for dashbar-relevant icons ===")
candidates = [
    "svr_home missing",  # placeholder filtered below
]
# Build from icons dir listing + common names referenced
icon_files = sorted(os.listdir(ICONS)) if os.path.isdir(ICONS) else []
relevant = [f for f in icon_files if f.startswith(("svr_", "icon_")) or "battery" in f or "volume" in f]
base = "/opt/steamvr/resources/webinterface/dashboard/images/icons"
print("ICON_DIR_COUNT", len(icon_files))
# Check paths that JS might resolve relative to dashboard
rel_paths = []
for name in relevant:
    rel_paths.append(f"{base}/{name}")
# Also check known dashboard images
extra = [
    "/opt/steamvr/resources/webinterface/dashboard/images/steam_spinner.png",
    "/opt/steamvr/resources/config/steamvr_dashboard_capsule.png",
    "/opt/steamvr/resources/reflections/dashboard_lights.png",
    "/opt/steamvr/resources/webinterface/dashboard/sounds/deck_ui_misc_10.wav",
    "/opt/steamvr/resources/webinterface/fonts",
]
for p in sorted(set(rel_paths + extra)):
    exists = os.path.exists(p)
    size = os.path.getsize(p) if exists and os.path.isfile(p) else ("DIR" if exists else "-")
    # Only print icons that look toolbar-relevant + extras
    bn = os.path.basename(p)
    if p in extra or any(k in bn for k in (
        "library", "menu", "settings", "desktop", "keyboard", "volume", "power",
        "quit", "mic", "theater", "more", "chat", "people", "store", "eye",
        "light", "night", "recenter", "room", "play", "home", "controls",
        "multitasking", "showdesktop", "camera", "close", "globe", "move",
        "items", "legacy", "screen", "curvature", "reset",
    )):
        print(("OK" if exists else "MISSING"), size, p)

print("\n=== SOUND refs near ControlBar ===")
for m in sorted(set(re.findall(r"/dashboard/sounds/[A-Za-z0-9_./-]+", alljs))):
    print(m)

print("\n=== Section / Group style enum near ControlBarGroup ===")
idx = alljs.find("ControlBarGroup")
while idx != -1:
    print(alljs[max(0, idx-120):idx+220].replace("\n", " "))
    print("---")
    idx = alljs.find("ControlBarGroup", idx+1)
    if idx > 0 and alljs.count("ControlBarGroup") > 20:
        # limit spam
        if alljs.find("ControlBarGroup", idx+1) and idx > alljs.find("ControlBarGroup")+5000:
            break
