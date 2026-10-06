#!/usr/bin/env python3
import re, os

js = open(
    "/opt/steamvr/resources/webinterface/dashboard/chunk~8012d0c89.js",
    encoding="utf-8",
    errors="replace",
).read()
css2 = open(
    "/opt/steamvr/resources/webinterface/dashboard/css/chunk~66c0d1388.css",
    encoding="utf-8",
    errors="replace",
).read()

print("=== Dashboard bar debug_name / id strings ===")
for pat in [
    r"LegacyDashboardBar",
    r"DashboardBar",
    r"MainControlBar",
    r"allowLegacyControlBar",
    r"StatusBar",
    r"ControlBarTray",
]:
    print(pat, js.count(pat))

print("\n=== Context around non-legacy ControlBar renders ===")
# find createElement with ControlBar that isn't MainControlBar
for m in re.finditer(r'className:"ControlBar[^"]*"', js):
    print(js[max(0, m.start() - 80) : m.end() + 120].replace("\n", " "))
    print("---")

print("\n=== :root / html.VROverlay assignments for control-bar* ===")
for sel in [r":root\{[^}]+\}", r"html\.VROverlay\{[^}]+\}"]:
    for m in re.finditer(sel, css2):
        block = m.group(0)
        hits = re.findall(
            r"--(?:dashboard-control-bar|control-bar)[a-z0-9-]*\s*:\s*[^;]+;",
            block,
        )
        if hits:
            print("SELECTOR", sel, "hits", len(hits))
            for h in hits:
                print(" ", h)

# Find which selector owns the control-bar vars (maybe not :root)
print("\n=== Any selector defining --control-bar-button-size: 96px ===")
parts = re.findall(r"[^{}]+\{[^{}]*\}", css2)
for p in parts:
    if "--control-bar-button-size: 96px" in p or "--dashboard-control-bar-component-padding: 21px" in p:
        sel = p.split("{", 1)[0].strip()
        print("SEL:", sel[:200])
        # print all control-bar / dashboard-control assignments in block
        for h in re.findall(
            r"--(?:dashboard-control-bar|control-bar|dashboard-status-bar|dashboard-minitoggle|settings-control-inner)[a-z0-9-]*\s*:\s*[^;]+;",
            p,
        ):
            print(" ", h)
        print("---")

print("\n=== Existence of bar-wired icons ===")
wired = [
    "svr_menu_c.svg",
    "svr_items.svg",
    "svr_desktop_alt.svg",
    "svr_more.svg",
    "svr_room_setup.svg",
    "svr_eye.svg",
    "svr_volume.svg",
    "svr_volume_mute.svg",
    "svr_volume_mirror.svg",
    "svr_volume_mirror_mute.svg",
    "svr_mic_active.svg",
    "svr_mic_mute.svg",
    "svr_settings.svg",
    "svr_app_quit.svg",
    "svr_svrhome_quit_alt.svg",
    "svr_play.svg",
    "icon_add.png",
    "icon_multitasking_view.png",
    "svr_recenter.svg",  # may be enum-rendered not path
    "svr_power.svg",
    "svr_keyboard.svg",
    "svr_library.svg",
    "svr_theater.svg",
]
base = "/opt/steamvr/resources/webinterface/dashboard/images/icons"
for name in wired:
    p = f"{base}/{name}"
    print(("OK" if os.path.exists(p) else "MISSING"), os.path.getsize(p) if os.path.exists(p) else "-", p)

print("\n=== Absolute runtime URL equivalents ===")
print("Web UI resolves /dashboard/... under SteamVR overlay HTTP root.")
print("On-disk equivalents:")
print("  /opt/steamvr/resources/webinterface/dashboard/images/icons/<file>")
print("  /opt/steamvr/resources/webinterface/dashboard/sounds/<file>")
print("  /opt/steamvr/resources/webinterface/fonts/<file>")
