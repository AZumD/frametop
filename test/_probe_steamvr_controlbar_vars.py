#!/usr/bin/env python3
"""Extract ControlBar CSS custom-property values and icon wiring from SteamVR systemui."""
import os
import re

ROOT = "/opt/steamvr/resources/webinterface"

def walk_css():
    for dirpath, _, files in os.walk(ROOT):
        for f in files:
            if f.endswith(".css") or f.endswith(".js"):
                yield os.path.join(dirpath, f)

keys = [
    "--gamepadui-darkest-grey",
    "--gamepadui-darker-grey",
    "--gamepadui-dark-grey",
    "--gamepadui-darkish-grey",
    "--gamepadui-soft-black",
    "--gamepadui-lightest-grey",
    "--dashboard-control-bar-width",
    "--dashboard-control-bar-height",
    "--dashboard-control-bar-side-padding",
    "--dashboard-control-bar-component-padding",
    "--dashboard-control-bar-control-spacing",
    "--dashboard-control-bar-volume-slider-width",
    "--dashboard-control-bar-now-playing-height",
    "--dashboard-control-bar-button-color-a",
    "--dashboard-control-bar-button-color-b",
    "--dashboard-control-bar-group-color-a",
    "--dashboard-control-bar-group-color-b",
    "--control-bar-button-size",
    "--control-bar-icon-size",
    "--control-bar-icon-size-large",
    "--control-bar-button-gradient-start-color",
    "--control-bar-button-gradient-end-color",
    "--control-bar-button-transition-time",
    "--control-bar-button-transition-ease",
    "--control-bar-tray-control-height",
    "--control-bar-tray-control-margin",
    "--control-bar-tray-section-spacing",
    "--settings-border-radius",
    "--settings-control-inner-border-radius",
    "--settings-control-outer-border-radius",
    "--settings-control-default-height",
    "--settings-control-hover-background",
    "--settings-control-box-hover-shadow",
    "--dashboard-status-bar-control-spacing",
    "--dashboard-minitoggle-color-a",
    "--dashboard-minitoggle-color-b",
]

print("=== VAR ASSIGNMENTS ACROSS webinterface ===")
found = {k: [] for k in keys}
for path in walk_css():
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        continue
    for k in keys:
        for m in re.finditer(re.escape(k) + r"\s*:\s*([^;]+);", text):
            val = m.group(1).strip()
            found[k].append((os.path.basename(path), val))

for k in keys:
    vals = found[k]
    if not vals:
        print(f"{k}: <not assigned in scanned files>")
        continue
    # unique
    uniq = []
    for item in vals:
        if item not in uniq:
            uniq.append(item)
    for src, val in uniq[:8]:
        print(f"{k}: {val}  [{src}]")

print("\n=== RGB companion vars ===")
rgb_keys = [
    "--gamepadui-darkest-grey-rgb",
    "--gamepadui-darker-grey-rgb",
    "--gamepadui-dark-grey-rgb",
    "--gamepadui-darkish-grey-rgb",
]
for path in walk_css():
    text = open(path, encoding="utf-8", errors="replace").read()
    for k in rgb_keys:
        for m in re.finditer(re.escape(k) + r"\s*:\s*([^;]+);", text):
            print(f"{k}: {m.group(1).strip()}  [{os.path.basename(path)}]")

print("\n=== ICON wiring snippets (images/icons near ControlBarButton) ===")
js = open(
    "/opt/steamvr/resources/webinterface/dashboard/chunk~8012d0c89.js",
    encoding="utf-8",
    errors="replace",
).read()
# Find consecutive image path assignments near MainControlBar
idx = js.find("MainControlBar")
print("MainControlBar context:")
print(js[max(0, idx - 200): idx + 2500])
print("\n====\n")
# Find all string literals that look like icon paths used with ControlBar buttons
for m in re.finditer(r".{0,80}images/icons/[^\"']+.{0,80}", js):
    s = m.group(0)
    if "ControlBar" in s or "svr_" in s or "icon_" in s:
        print(s.replace("\n", " ")[:300])
        print("---")

print("\n=== allowLegacyControlBar / settings path ===")
for m in re.finditer(r".{0,60}allowLegacyControlBar.{0,60}", js):
    print(m.group(0))

print("\n=== Pseudo-element bloom (:before) rule for ControlBarButton ===")
css = open(
    "/opt/steamvr/resources/webinterface/dashboard/css/chunk~93a8598f9.css",
    encoding="utf-8",
    errors="replace",
).read()
for m in re.finditer(r"[^{}]*ControlBarButton[^{}]*:before[^{}]*\{[^{}]*\}", css):
    print(m.group(0))
    print("---")
for m in re.finditer(r"[^{}]*ControlBarButton[^{}]*::?before[^{}]*\{[^{}]*\}", css):
    print(m.group(0))
    print("---")
# also look for gradient start/end used as before content
for m in re.finditer(r"[^{}]*control-bar-button-gradient[^{}]*\{[^{}]*\}", css):
    print(m.group(0))
    print("---")

print("\n=== FONTS used by systemui ===")
html = open(
    "/opt/steamvr/resources/webinterface/dashboard/systemui.html",
    encoding="utf-8",
    errors="replace",
).read()
print(html)
print("font files:")
for f in sorted(os.listdir("/opt/steamvr/resources/webinterface/fonts")):
    p = os.path.join("/opt/steamvr/resources/webinterface/fonts", f)
    print(f, os.path.getsize(p))

print("\n=== shared/ webinterface ===")
for dirpath, _, files in os.walk("/opt/steamvr/resources/webinterface/shared"):
    for f in files:
        print(os.path.join(dirpath, f), os.path.getsize(os.path.join(dirpath, f)))
