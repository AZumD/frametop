#!/usr/bin/env python3
import re

css = open(
    "/opt/steamvr/resources/webinterface/dashboard/css/chunk~93a8598f9.css",
    encoding="utf-8",
    errors="replace",
).read()
css2 = open(
    "/opt/steamvr/resources/webinterface/dashboard/css/chunk~66c0d1388.css",
    encoding="utf-8",
    errors="replace",
).read()

# Find all rules mentioning ControlBarButton and :before in selector or body
parts = re.findall(r"[^{}]+\{[^{}]*\}", css + css2)
print("=== All rules with ControlBarButton AND (before OR gradient OR filter OR opacity) ===")
for p in parts:
    if "ControlBarButton" in p and any(
        x in p for x in [":before", "::before", "gradient", "filter", "opacity", "content:"]
    ):
        print(p.strip())
        print("---")

print("\n=== Rules defining :before for buttons generally near control bar ===")
for p in parts:
    sel = p.split("{", 1)[0]
    if ":before" in sel or "::before" in sel:
        if any(x in sel for x in ["ControlBar", "ButtonControl", "GamepadUI", "gamepadui"]):
            print(p.strip()[:1000])
            print("---")

print("\n=== html.VROverlay dashboard-control-bar var subset ===")
m = re.search(r"html\.VROverlay\{[^}]+\}", css2)
if m:
    block = m.group(0)
    # pretty print key vars
    for key in [
        "dashboard-control-bar",
        "control-bar",
        "settings-border-radius",
        "settings-control-inner",
        "gamepadui",
    ]:
        for mm in re.finditer(r"--[^:;]*" + key + r"[^:]*:[^;]+;", block):
            print(mm.group(0))

print("\n=== Full html.VROverlay length and control-bar lines ===")
if m:
    # extract only assignments containing control-bar or settings-border
    for mm in re.finditer(
        r"--(?:dashboard-control-bar|control-bar|settings-border-radius|settings-control-inner-border-radius|settings-button-border-radius)[^:]*:[^;]+;",
        m.group(0),
    ):
        print(mm.group(0))

# Also look for ControlBarButton:before base style without hover - maybe split across
print("\n=== Search raw for ControlBarButton:before content ===")
idx = 0
while True:
    i = css.find("ControlBarButton:before", idx)
    if i < 0:
        i = css.find("ControlBarButton::before", idx)
    if i < 0:
        break
    print(css[max(0, i - 200) : i + 400])
    print("---SNAP---")
    idx = i + 20

# gradient vars usage
print("\n=== control-bar-button-gradient usage ===")
for m in re.finditer(r".{0,120}control-bar-button-gradient.{0,200}", css + css2):
    print(m.group(0))
    print("---")

# gamepaduibutton before (might be shared bloom pattern)
print("\n=== GamepadUIButton:before (related hover bloom pattern) ===")
for p in parts:
    if "GamepadUIButton" in p and ":before" in p.split("{")[0]:
        print(p.strip()[:800])
        print("---")
