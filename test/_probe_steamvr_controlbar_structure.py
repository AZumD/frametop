#!/usr/bin/env python3
"""Deeper structure: Right section buttons, :before bloom, BlackToWhite, border radius context."""
import re

js = open(
    "/opt/steamvr/resources/webinterface/dashboard/chunk~8012d0c89.js",
    encoding="utf-8",
    errors="replace",
).read()
css = open(
    "/opt/steamvr/resources/webinterface/dashboard/css/chunk~93a8598f9.css",
    encoding="utf-8",
    errors="replace",
).read()
css_vars = open(
    "/opt/steamvr/resources/webinterface/dashboard/css/chunk~66c0d1388.css",
    encoding="utf-8",
    errors="replace",
).read()

idx = js.find('className:"ControlBar MainControlBar"')
print("=== FULL MainControlBar render (~4k) ===")
print(js[idx: idx + 4500])

print("\n=== ControlBarButton :before / gradient definitions ===")
# find rules mentioning control-bar-button-gradient or ControlBarButton:before content
for pat in [
    r"[^{}]*ControlBarButton[^{}:]*::?before[^{}]*\{[^{}]*\}",
    r"[^{}]*\.ControlBarButton[^{}]*\{[^{}]*(?:gradient|before|after)[^{}]*\}",
    r"[^{}]*BlackToWhite[^{}]*\{[^{}]*\}",
    r"[^{}]*CenterImage[^{}]*\{[^{}]*\}",
]:
    print("PAT", pat)
    for m in re.finditer(pat, css + css_vars):
        print(m.group(0)[:800])
        print("---")

print("\n=== DashboardMain theme block with settings-border-radius near control bar ===")
# Find DashboardMain { ... } with many vars
for m in re.finditer(r"\.DashboardMain\{[^}]+\}", css_vars):
    print(m.group(0)[:4000])
    print("---")
for m in re.finditer(r"\.DashboardMain\{[^}]+\}", css):
    print("from 93a:", m.group(0)[:2000])
    print("---")

# Find which selector sets --settings-border-radius: 30px
print("\n=== selectors setting --settings-border-radius ===")
parts = re.findall(r"[^{}]+\{[^{}]*\}", css_vars)
for p in parts:
    if "--settings-border-radius:" in p:
        print(p.strip()[:500])
        print("---")

print("\n=== icon enum map (case N: url) ===")
for m in re.finditer(
    r"case\s+(\d+):return\s+n\.createElement\([^{;]{0,40}url:\"(/dashboard/images/icons/[^\"]+)\"",
    js,
):
    print(m.group(1), m.group(2))

print("\n=== legacyImageUrl unique set ===")
for u in sorted(set(re.findall(r'legacyImageUrl:"(/dashboard/images/icons/[^"]+)"', js))):
    print(u)
for u in sorted(set(re.findall(r'legacyImageUrl:([A-Za-z0-9_.]+)', js))):
    print("dyn", u)

print("\n=== iconUrl unique ===")
for u in sorted(set(re.findall(r'iconUrl:"(/dashboard/images/icons/[^"]+)"', js))):
    print(u)

print("\n=== Power / Settings / Volume button bits ===")
for key in ["svr_settings", "svr_power", "svr_volume", "svr_keyboard", "svr_nightmode", "svr_lightmode", "svr_theater", "svr_chat", "svr_recenter"]:
    for m in re.finditer(r".{0,100}" + key + r".{0,100}", js):
        print(m.group(0).replace("\n", " ")[:250])
        print("---")
        break
