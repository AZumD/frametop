#!/usr/bin/env python3
"""Merge Stage-2 toolbar helpers into layout/ft_layout.py."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = Path("/mnt/c/Users/Antho/Projects/frametop-stage1-chrome/layout/ft_layout.py")
DST = ROOT / "layout" / "ft_layout.py"

src = SRC.read_text(encoding="utf-8")
dst = DST.read_text(encoding="utf-8")

# --- import ---
if "import ft_toolbar" not in dst:
    m = re.search(
        r"try:\n    import ft_desktop\nexcept ImportError:\n    ft_desktop = None[^\n]*\n",
        dst,
    )
    if not m:
        raise SystemExit("ft_desktop import block missing")
    insert = (
        m.group(0)
        + "\ntry:\n    import ft_toolbar\nexcept ImportError:\n    ft_toolbar = None\n"
    )
    dst = dst[: m.start()] + insert + dst[m.end() :]
    print("added ft_toolbar import")

# --- DEFAULTS ---
old_defaults = (
    'DEFAULTS = {"auto": True, "mode": "preset",\n'
    '            "preset": {"kind": "arc", "rows": 1, "distance": 2.0, "gap": 0.05, "height": 0.0},\n'
    '            "screens": [], "instruments": [], "panel_size": list(DEFAULT_PANEL)}'
)
new_defaults = (
    'DEFAULTS = {"auto": True, "mode": "preset",\n'
    '            "preset": {"kind": "arc", "rows": 1, "distance": 2.0, "gap": 0.05, "height": 0.0},\n'
    '            "screens": [], "instruments": [], "panel_size": list(DEFAULT_PANEL),\n'
    '            "toolbar": {"enabled": True}}'
)
if '"toolbar"' not in dst.split("DEFAULTS", 1)[1][:600]:
    if old_defaults not in dst:
        raise SystemExit("DEFAULTS block not found")
    dst = dst.replace(old_defaults, new_defaults, 1)
    print("DEFAULTS toolbar enabled=True")

# PROFILE_SCREEN_KEYS add dock
if '"dock"' not in dst.split("PROFILE_SCREEN_KEYS", 1)[1][:300]:
    dst = dst.replace(
        'PROFILE_SCREEN_KEYS = ("pos", "face", "roll", "metres", "curve", "pin", "opacity",\n'
        '                       "active_opacity", "idle_opacity", "attention", "follow_deadzone", "hidden")',
        'PROFILE_SCREEN_KEYS = ("pos", "face", "roll", "metres", "curve", "pin", "opacity",\n'
        '                       "active_opacity", "idle_opacity", "attention", "follow_deadzone", "hidden",\n'
        '                       "dock")',
        1,
    )
    print("PROFILE_SCREEN_KEYS +dock")

# --- load_layout sanitize toolbar (always enable if missing) ---
old_load_tail = """    if backend() == "screens" and not layout.get("screens"):
        layout["screens"] = [{"size": [1920, 1080], "metres": 1920 / PIXELS_PER_METRE}]
    return layout
"""
new_load_tail = """    if backend() == "screens" and not layout.get("screens"):
        layout["screens"] = [{"size": [1920, 1080], "metres": 1920 / PIXELS_PER_METRE}]
    if ft_toolbar is not None:
        tb = ft_toolbar.sanitize_toolbar(layout.get("toolbar"))
        if tb is None:
            layout["toolbar"] = ft_toolbar.default_toolbar()
        else:
            # Rock-solid: once toolbar code is present, keep it enabled unless explicitly off.
            if "enabled" not in (layout.get("toolbar") or {}):
                tb["enabled"] = True
            layout["toolbar"] = tb
    elif "toolbar" not in layout:
        layout["toolbar"] = {"enabled": True}
    return layout
"""
if "ft_toolbar.sanitize_toolbar" not in dst:
    if old_load_tail not in dst:
        raise SystemExit("load_layout tail not found")
    dst = dst.replace(old_load_tail, new_load_tail, 1)
    print("load_layout toolbar sanitize")

# --- helper screen_dock ---
if "def screen_dock(" not in dst:
    m = re.search(r"^def screen_dock\(.*?(?=^def )", src, flags=re.M | re.S)
    if not m:
        raise SystemExit("screen_dock missing in stage1")
    # insert before screen_entry
    if "def screen_entry(" not in dst:
        raise SystemExit("screen_entry missing")
    dst = dst.replace("def screen_entry(", m.group(0).rstrip() + "\n\n\ndef screen_entry(", 1)
    print("added screen_dock")

# --- main toolbar functions ---
funcs = []
for name in (
    "apply_toolbar",
    "apply_docks",
    "parse_dock_state",
    "dock_layout",
    "dock_sync",
    "capture_toolbar",
    "save_toolbar_capture",
    "toolbar_cmd",
    "dock_cmd",
):
    m = re.search(rf"^def {name}\(.*?(?=^def |\Z)", src, flags=re.M | re.S)
    if not m:
        raise SystemExit(f"missing {name} in stage1")
    funcs.append(m.group(0).rstrip() + "\n\n")
    print("got", name, len(m.group(0)))

if "def apply_toolbar(" not in dst:
    block = "".join(funcs)
    if "def apply_instruments(" not in dst:
        raise SystemExit("apply_instruments not found")
    dst = dst.replace("def apply_instruments(", block + "def apply_instruments(", 1)
    print("inserted toolbar functions before apply_instruments")

# --- wire apply_screens ---
if "apply_toolbar(sock, layout)" not in dst:
    old = "    apply_instruments(sock, layout)\n"
    # Only the one inside apply_screens — first occurrence after def apply_screens
    idx = dst.find("def apply_screens(")
    if idx < 0:
        raise SystemExit("apply_screens missing")
    pos = dst.find(old, idx)
    if pos < 0:
        raise SystemExit("apply_instruments call in apply_screens missing")
    dst = dst[:pos] + "    apply_toolbar(sock, layout)\n" + dst[pos:]
    print("wired apply_toolbar into apply_screens")

# --- CLI ---
if 'elif cmd == "toolbar"' not in dst:
    if 'elif cmd == "screen-args":' not in dst:
        raise SystemExit("screen-args CLI missing")
    dst = dst.replace(
        'elif cmd == "screen-args":',
        'elif cmd == "toolbar":\n            return toolbar_cmd(argv)\n'
        '        elif cmd == "dock":\n            return dock_cmd(argv)\n'
        '        elif cmd == "screen-args":',
        1,
    )
    print("wired CLI toolbar/dock")

DST.write_text(dst, encoding="utf-8")
print("wrote", DST, "bytes", len(dst))
