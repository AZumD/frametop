#!/usr/bin/env python3
"""ft-layout: the Frametop screens' sizes and where they float around you.

Two desktop backends (BACKEND in ~/.config/frametop.conf):
  screens    (default) ft-screens, our own compositor (screens): each screen
             is its own SteamVR panel with its own resolution and size in metres. ft-layout
             places them directly through ft-screens' control socket (@ft_screens).
  gamescope  the old path: every screen one size (at most 1920x1080 worth of pixels),
             panels owned by the SteamVR dashboard, so ft-layout floats each one with
             `vrcmd --dock-overlay` and the pointer helper carries it into place.

The layout is relative to your head when it's applied: its position and the direction
you face (yaw only), like a recenter. It lives in ~/.config/frametop-layout.json:
  {"auto": true,                      arrange when the desktop starts
   "mode": "preset" | "custom",
   "preset": {"kind": "arc" | "flat", "rows": 1, "distance": 2.0, "gap": 0.05, "height": 0},
   "primary": 2,                      the screen with the taskbar (1-based; default: the biggest)
   "visibility": {"mode": "always",   ft-screens: always | dashboard (only with the SteamVR
                  "wrist_angle": 60,    dashboard open) | gesture (while you look at a controller)
                  "gesture_hand": "left", "gesture_angle": 20},   | toggle (hidden until shown);
                                      wrist_angle: a controller-pinned screen shows while you see
                                      its front within this many degrees
   "screens": [{"size": [w, h], "metres": 3.6,        ft-screens: pixels, and width in VR
                "curve": 0,                           ft-screens: cylinder radius in metres, 0 = flat
                "pin": {"anchor": "left"|"right"|"head", "rel": [12],
                        "hand": "left"},              ft-screens: tracked-device anchor (hand kept
                                                      for left/right for older readers)
                "scale": 1.0,                         KWin output scale (1.0 = 100%)
                "pos": [x, y, z], "face": [yaw, pitch], "roll": 0,   custom layout
                "rotation": "normal" | "left" | "right"}, ...],      gamescope only
   "instruments": [{"id": "clock", "type": "clock", "enabled": true,  Spatial Instruments (ambient VR
                     "pos"/"face"/"roll" or "pin", "metres",            info outside virtual displays;
                     "active_opacity", "idle_opacity", "attention"}],   Clock is the first type)
   "panel_size": [w, h]}              gamescope: last measured panel size

Named spatial profiles (same screen count; no resolution/scale/visibility) live in
~/.config/frametop-layout-profiles.json and may include instruments. Old files without
instruments still load (empty instruments). The active layout file stays compatible.

Custom positions: x right, y up, -z forward from the head, in metres; face = the
direction you look to see the screen's front straight on, in degrees, relative to your
heading; roll = the panel turned about its front, counterclockwise as you see it.
Presets: "arc" hinges the screens edge to edge around you, each turned to face you
(like monitors on a desk); "flat" puts them on one flat wall facing forward. Screen 1
is top left, then left to right.

Usage (on the Frame host; Frametop Display Settings calls it too):
  ft-layout apply [--wait SECONDS] [--duration MS]
  ft-layout capture                  save the current arrangement as the custom layout
  ft-layout plan                     print the arrangement as JSON (no VR needed)
  ft-layout scale                    per-screen scale, positions, and primary to KWin
  ft-layout screen-args              ft-screens' --screen arguments for the session script
  ft-layout screen state --json      per-screen anchor/opacity + slot info
  ft-layout gaze state               true eye-tracking status + current gaze target
  ft-layout gaze debug on|off
  ft-layout gaze fallback head|off   explicit head-direction fallback (debug only)
  ft-layout action NAME [--duration MS]   # semantic actions (chrome / input / Quickshell)
  ft-layout action list [--json]
  ft-layout toggle                   hide or show all screens (ft-screens)
  ft-layout pin all|N left|right|head|head-rigid|yaw-follow|position-follow
  ft-layout opacity N ACTIVE [IDLE]  # live + layout; default idle=ACTIVE; also turns attention off
  ft-layout profile list [--json]
  ft-layout profile current [--json]
  ft-layout profile save NAME
  ft-layout profile apply NAME [--duration MS]   # default duration 450; 0 = instant
  ft-layout profile delete NAME
  ft-layout profile slot N NAME | unslot N | slots [--json]
  ft-layout profile apply-slot N [--duration MS]
  ft-layout profile next|previous [--duration MS]
  ft-layout instrument list|state [--json]
  ft-layout instrument enable|disable|recenter clock
"""
import json
import math
import os
import re
import socket
import subprocess
import sys
import time

try:
    import fcntl
except ImportError:  # Windows unit tests; Frame always has fcntl
    fcntl = None

LAYOUT_PATH = os.path.expanduser("~/.config/frametop-layout.json")
PROFILES_PATH = os.path.expanduser("~/.config/frametop-layout-profiles.json")
CONF_PATH = os.path.expanduser("~/.config/frametop.conf")
VRCMD = "/opt/steamvr/bin/linuxarm64/vrcmd"
HELPER = "\0ft_pointer_helper"
SCREENS = "\0ft_screens"
LOCK_PATH = "/tmp/ft-layout.lock"
DEFAULT_PANEL = (1.18, 0.664)  # gamescope: a floating 16:9 dashboard panel, measured on the Frame
PIXELS_PER_METRE = 800         # ft-screens: a new screen's default size in VR (1920 px: 2.4 m)
# controllers: when controllers' lasers work the screens (always | outside_games | dashboard).
# in_games: during a VR game, "always" hides the screens unless the dashboard is open (hide),
# or leaves them up (visible).
VISIBILITY = {"mode": "always", "wrist_angle": 60, "gesture_hand": "left", "gesture_angle": 20,
              "controllers": "outside_games", "in_games": "hide"}
DEFAULTS = {"auto": True, "mode": "preset",
            "preset": {"kind": "arc", "rows": 1, "distance": 2.0, "gap": 0.05, "height": 0.0},
            "screens": [], "instruments": [], "panel_size": list(DEFAULT_PANEL)}
# Spatial fields stored in a named profile (not resolution/scale/primary/visibility).
PROFILE_SCREEN_KEYS = ("pos", "face", "roll", "metres", "curve", "pin", "opacity",
                       "active_opacity", "idle_opacity", "attention", "follow_deadzone")
# Follow modes. Legacy pin anchor/hand "head" means soft head (HeadSoft).
ANCHOR_MODES = ("world", "left", "right", "head", "head-rigid", "yaw-follow", "position-follow")
INSTRUMENT_ANCHORS = ("world", "head", "head-rigid", "yaw-follow", "position-follow")
KNOWN_INSTRUMENT_TYPES = ("clock",)
CONTROLLER_ANCHORS = ("left", "right")
SOFT_FOLLOW_ANCHORS = ("head", "yaw-follow", "position-follow")
SLOT_COUNT = 6
DEFAULT_PROFILE_DURATION_MS = 450
DEFAULT_FOLLOW_LAG_MS = 120
DEFAULT_OPACITY = 1.0
DEFAULT_INSTRUMENT_METRES = 0.35
DEFAULT_INSTRUMENT_IDLE = 0.35
DEFAULT_ATTENTION_IN_MS = 150.0
DEFAULT_ATTENTION_OUT_MS = 250.0
DEFAULT_ATTENTION_DWELL_MS = 80.0
DEFAULT_ATTENTION_HOLD_MS = 150.0
DEFAULT_FOLLOW_DEADZONE_DEG = 15.0
DEFAULT_FOLLOW_DEADZONE_M = 0.15


def log(*args, **kwargs):
    kwargs.setdefault("flush", True)
    print(*args, **kwargs)


# ---------------------------------------------------------------- config

def read_conf():
    conf = {}
    try:
        with open(CONF_PATH) as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                if "=" in line:
                    k, v = line.split("=", 1)
                    conf[k.strip()] = v.strip()
    except OSError:
        pass
    return conf


def backend():
    return "gamescope" if read_conf().get("BACKEND", "screens") == "gamescope" else "screens"


def screen_count(layout=None):
    """ft-screens: the configured screens; gamescope: SCREENS."""
    if backend() == "screens":
        return max(1, len((layout or load_layout()).get("screens", [])))
    try:
        return max(1, int(read_conf().get("SCREENS", "2")))
    except ValueError:
        return 2


def load_layout():
    layout = json.loads(json.dumps(DEFAULTS))
    try:
        with open(LAYOUT_PATH) as f:
            saved = json.load(f)
        layout.update({k: v for k, v in saved.items() if k != "preset"})
        layout["preset"].update(saved.get("preset", {}))
    except (OSError, ValueError):
        pass
    if backend() == "screens" and not layout.get("screens"):
        layout["screens"] = [{"size": [1920, 1080], "metres": 1920 / PIXELS_PER_METRE}]
    return layout


def save_layout(layout):
    os.makedirs(os.path.dirname(LAYOUT_PATH), exist_ok=True)
    tmp = LAYOUT_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(layout, f, indent=2)
    os.replace(tmp, LAYOUT_PATH)


def atomic_write_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def normalize_anchor(name):
    """Map a pin/anchor string to a canonical mode. Legacy 'head' stays 'head' (soft)."""
    if not name or name in ("none", "world"):
        return "world"
    if name in ANCHOR_MODES:
        return name
    return None


def pin_anchor(pin):
    """Canonical follow mode from a pin dict: prefer 'anchor', fall back to legacy 'hand'."""
    if not isinstance(pin, dict):
        return None
    return normalize_anchor(pin.get("anchor") or pin.get("hand"))


def make_pin(anchor, rel):
    """Pin dict for layout JSON. Keeps legacy 'hand' for left/right/head."""
    anchor = normalize_anchor(anchor)
    if not anchor or anchor == "world":
        return None
    pin = {"anchor": anchor, "rel": [float(v) for v in rel]}
    if anchor in ("left", "right", "head"):
        pin["hand"] = anchor  # iteration-1 readers; head => soft
    return pin


def screen_opacity(entry):
    """Legacy single opacity (active). Prefer screen_opacities() for idle/active."""
    try:
        if "active_opacity" in entry:
            return max(0.0, min(1.0, float(entry["active_opacity"])))
        return max(0.0, min(1.0, float(entry.get("opacity", DEFAULT_OPACITY))))
    except (TypeError, ValueError):
        return DEFAULT_OPACITY


def screen_opacities(entry):
    """Return (active, idle). Legacy opacity=X means both active and idle = X, attention off."""
    active = screen_opacity(entry)
    try:
        if "idle_opacity" in entry:
            idle = max(0.0, min(1.0, float(entry["idle_opacity"])))
        else:
            idle = active
    except (TypeError, ValueError):
        idle = active
    return active, idle


def composed_attention_alpha(idle, active, focused, resolved, visibility=1.0):
    """Model final overlay alpha: attentionResolved * visibility (unit-test helper)."""
    target = active if focused else idle
    # resolved is the smoothed value already; visibility is independent.
    return max(0.0, min(1.0, float(resolved) * float(visibility))), float(target)


def screen_attention(entry):
    """Optional true-eye-gaze attention fade (idle↔active). Legacy head-angle fields ignored."""
    a = entry.get("attention")
    if not isinstance(a, dict):
        return {
            "enabled": False,
            "in_ms": DEFAULT_ATTENTION_IN_MS,
            "out_ms": DEFAULT_ATTENTION_OUT_MS,
            "dwell_ms": DEFAULT_ATTENTION_DWELL_MS,
            "hold_ms": DEFAULT_ATTENTION_HOLD_MS,
        }
    return {
        "enabled": bool(a.get("enabled", False)),
        "in_ms": float(a.get("in_ms", a.get("fade_in_ms", DEFAULT_ATTENTION_IN_MS))),
        "out_ms": float(a.get("out_ms", a.get("fade_out_ms", DEFAULT_ATTENTION_OUT_MS))),
        "dwell_ms": float(a.get("dwell_ms", DEFAULT_ATTENTION_DWELL_MS)),
        "hold_ms": float(a.get("hold_ms", DEFAULT_ATTENTION_HOLD_MS)),
    }


def screen_follow_deadzone(entry):
    """Soft-follow glance dead zone (degrees + metres). Off unless enabled."""
    d = entry.get("follow_deadzone")
    if not isinstance(d, dict):
        return {
            "enabled": False,
            "degrees": DEFAULT_FOLLOW_DEADZONE_DEG,
            "metres": DEFAULT_FOLLOW_DEADZONE_M,
        }
    return {
        "enabled": bool(d.get("enabled", False)),
        "degrees": max(1.0, min(90.0, float(d.get("degrees", DEFAULT_FOLLOW_DEADZONE_DEG)))),
        "metres": max(0.02, min(1.0, float(d.get("metres", DEFAULT_FOLLOW_DEADZONE_M)))),
    }


def spatial_screen(entry):
    """Profile payload for one screen (spatial only)."""
    out = {}
    for k in PROFILE_SCREEN_KEYS:
        if k in ("pin", "attention", "opacity", "active_opacity", "idle_opacity", "follow_deadzone"):
            continue
        if k in entry:
            out[k] = entry[k]
    active, idle = screen_opacities(entry)
    out["opacity"] = round(active, 3)  # legacy readers
    out["active_opacity"] = round(active, 3)
    out["idle_opacity"] = round(idle, 3)
    pin = entry.get("pin")
    anchor = pin_anchor(pin)
    if anchor and anchor != "world" and isinstance(pin, dict) and len(pin.get("rel", [])) == 12:
        out["pin"] = make_pin(anchor, pin["rel"])
    att = screen_attention(entry)
    if att["enabled"]:
        out["attention"] = att
    dz = screen_follow_deadzone(entry)
    if dz["enabled"]:
        out["follow_deadzone"] = {
            "enabled": True,
            "degrees": round(dz["degrees"], 1),
            "metres": round(dz["metres"], 3),
        }
    return out


def default_clock_instrument():
    return {
        "id": "clock",
        "type": "clock",
        "enabled": False,
        "metres": DEFAULT_INSTRUMENT_METRES,
        "active_opacity": 1.0,
        "idle_opacity": DEFAULT_INSTRUMENT_IDLE,
        "opacity": 1.0,
        "attention": {
            "enabled": True,
            "in_ms": DEFAULT_ATTENTION_IN_MS,
            "out_ms": DEFAULT_ATTENTION_OUT_MS,
            "dwell_ms": DEFAULT_ATTENTION_DWELL_MS,
            "hold_ms": DEFAULT_ATTENTION_HOLD_MS,
        },
    }


def normalize_instrument(entry, warn=True):
    """Sanitize one instrument dict. Unknown types return None (skipped safely)."""
    if not isinstance(entry, dict):
        if warn:
            log("warning: ignoring non-object instrument entry", file=sys.stderr)
        return None
    itype = str(entry.get("type") or "").strip().lower()
    if itype not in KNOWN_INSTRUMENT_TYPES:
        if warn:
            log(f"warning: ignoring unknown instrument type {itype!r}", file=sys.stderr)
        return None
    iid = str(entry.get("id") or itype).strip() or itype
    out = default_clock_instrument() if itype == "clock" else {"id": iid, "type": itype}
    out["id"] = iid
    out["type"] = itype
    out["enabled"] = bool(entry.get("enabled", False))
    try:
        out["metres"] = max(0.08, min(2.0, float(entry.get("metres", DEFAULT_INSTRUMENT_METRES))))
    except (TypeError, ValueError):
        out["metres"] = DEFAULT_INSTRUMENT_METRES
    active, idle = screen_opacities(entry if ("active_opacity" in entry or "idle_opacity" in entry
                                             or "opacity" in entry) else {
        "active_opacity": out["active_opacity"], "idle_opacity": out["idle_opacity"]})
    # Prefer explicit fields when present.
    try:
        if "active_opacity" in entry:
            active = max(0.0, min(1.0, float(entry["active_opacity"])))
        elif "opacity" in entry:
            active = max(0.0, min(1.0, float(entry["opacity"])))
    except (TypeError, ValueError):
        pass
    try:
        if "idle_opacity" in entry:
            idle = max(0.0, min(1.0, float(entry["idle_opacity"])))
        elif "opacity" in entry and "active_opacity" not in entry:
            idle = active
    except (TypeError, ValueError):
        idle = active
    out["active_opacity"] = round(active, 3)
    out["idle_opacity"] = round(idle, 3)
    out["opacity"] = round(active, 3)
    for k in ("pos", "face", "roll"):
        if k in entry:
            out[k] = entry[k]
    pin = entry.get("pin")
    anchor = pin_anchor(pin)
    if anchor and anchor in INSTRUMENT_ANCHORS and anchor != "world" and isinstance(pin, dict) \
            and len(pin.get("rel", [])) == 12:
        out["pin"] = make_pin(anchor, pin["rel"])
    else:
        out.pop("pin", None)
    att = screen_attention(entry)
    out["attention"] = att
    return out


def instruments_from_layout(layout):
    """Return sanitized instruments list (unknown types dropped)."""
    raw = layout.get("instruments") if isinstance(layout, dict) else None
    if raw is None:
        return []
    if not isinstance(raw, list):
        log("warning: instruments field is not a list; treating as empty", file=sys.stderr)
        return []
    out, seen = [], set()
    for entry in raw:
        inst = normalize_instrument(entry)
        if not inst:
            continue
        if inst["id"] in seen:
            log(f"warning: duplicate instrument id {inst['id']!r}; keeping first", file=sys.stderr)
            continue
        seen.add(inst["id"])
        out.append(inst)
    return out


def spatial_instrument(entry):
    """Profile payload for one instrument."""
    inst = normalize_instrument(entry, warn=False)
    if not inst:
        return None
    out = {
        "id": inst["id"],
        "type": inst["type"],
        "enabled": bool(inst["enabled"]),
        "metres": round(float(inst["metres"]), 4),
        "opacity": round(float(inst["active_opacity"]), 3),
        "active_opacity": round(float(inst["active_opacity"]), 3),
        "idle_opacity": round(float(inst["idle_opacity"]), 3),
    }
    for k in ("pos", "face", "roll"):
        if k in inst:
            out[k] = inst[k]
    if inst.get("pin"):
        out["pin"] = inst["pin"]
    att = inst.get("attention") or {}
    if att.get("enabled"):
        out["attention"] = att
    return out


def instrument_entry(layout, iid):
    for inst in instruments_from_layout(layout):
        if inst["id"] == iid:
            return inst
    return None


def upsert_instrument(layout, inst):
    layout = json.loads(json.dumps(layout))
    items = instruments_from_layout(layout)
    found = False
    for i, cur in enumerate(items):
        if cur["id"] == inst["id"]:
            items[i] = normalize_instrument(inst)
            found = True
            break
    if not found:
        items.append(normalize_instrument(inst))
    layout["instruments"] = [x for x in items if x]
    return layout


def screen_entry(layout, i):
    screens = layout.get("screens", [])
    return screens[i] if i < len(screens) else {}


def screen_scale(layout, i):
    return float(screen_entry(layout, i).get("scale", 1.0))


def screen_pixels(layout, i):
    w, h = screen_entry(layout, i).get("size", [1920, 1080])
    return int(w), int(h)


def screen_metres(layout, i):
    w, _ = screen_pixels(layout, i)
    return float(screen_entry(layout, i).get("metres", w / PIXELS_PER_METRE))


ROLL = {"normal": 0.0, "left": 90.0, "right": -90.0}


def screen_rotation(layout, i):
    if backend() == "screens":
        return "normal"  # portrait screens are simply tall
    r = screen_entry(layout, i).get("rotation", "normal")
    return r if r in ROLL else "normal"


def screen_size(layout, i, panel_size=None):
    """A screen's size in VR (width, height) in metres."""
    if backend() == "screens":
        w, h = screen_pixels(layout, i)
        m = screen_metres(layout, i)
        return m, m * h / w
    w, h = panel_size or layout.get("panel_size") or DEFAULT_PANEL
    return (h, w) if screen_rotation(layout, i) != "normal" else (w, h)


def primary_screen(layout):
    """0-based index of the screen with the taskbar: the chosen one, or the biggest."""
    n = screen_count(layout)
    p = layout.get("primary")
    if isinstance(p, int) and 1 <= p <= n:
        return p - 1
    return max(range(n), key=lambda i: screen_pixels(layout, i)[0] * screen_pixels(layout, i)[1])


# ---------------------------------------------------------------- geometry
# Head frame: x right, y up, -z forward, at the eye, turned to the heading (yaw).
# yaw 0 = -Z, positive yaw turns left, positive pitch looks up (as in SteamVR's helper).

def direction(yaw, pitch):
    y, p = math.radians(yaw), math.radians(pitch)
    return (-math.sin(y) * math.cos(p), math.sin(p), -math.cos(y) * math.cos(p))


def yaw_pitch(v):
    n = math.sqrt(sum(c * c for c in v)) or 1.0
    return math.degrees(math.atan2(-v[0], -v[2])), math.degrees(math.asin(max(-1.0, min(1.0, v[1] / n))))


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def normalize(v):
    n = math.sqrt(dot(v, v)) or 1.0
    return tuple(c / n for c in v)


def turn_yaw(v, yaw):
    """Rotate v about +Y by yaw degrees (head frame -> world for the heading yaw)."""
    s, c = math.sin(math.radians(yaw)), math.cos(math.radians(yaw))
    return (v[0] * c + v[2] * s, v[1], -v[0] * s + v[2] * c)


def _chain(widths, d, gap):
    """One row of flat screens hinged edge to edge around the eye, each turned to face it,
    like monitors on a desk: the middle screen (or the seam between the middle two) is
    straight ahead at distance d; each neighbour starts at the previous screen's outer
    edge (plus the gap) and is turned until it faces the eye. Returns [(x, z, yaw)], in
    the head frame from above (x right, -z forward)."""
    n = len(widths)
    out = [None] * n

    def right(yaw):  # a screen's right vector for its yaw
        return math.cos(math.radians(yaw)), -math.sin(math.radians(yaw))

    def yaw_of(x, z):
        return math.degrees(math.atan2(-x, -z))

    def hang(hinge, w, side):
        # Turn the screen about its hinge until it faces the eye: its centre
        # C = hinge + side * w/2 * right(yaw) must have no sideways part, dot(C, right) = 0,
        # that is dot(hinge, right(yaw)) = -side * w/2. Take the root nearest the hinge's
        # own direction, turning outward (right: yaw falls; left: yaw rises).
        def g(yaw):
            rx, rz = right(yaw)
            return hinge[0] * rx + hinge[1] * rz + side * w / 2
        start = yaw_of(*hinge)
        a, ga = start, g(start)
        for k in range(1, 721):  # 0.25-degree steps, up to half a turn
            b = start - side * k * 0.25
            gb = g(b)
            if ga == 0 or ga * gb < 0:
                for _ in range(50):
                    mid = (a + b) / 2
                    if g(a) * g(mid) <= 0:
                        b = mid
                    else:
                        a = mid
                break
            a, ga = b, gb
        yaw = a
        rx, rz = right(yaw)
        return hinge[0] + side * rx * w / 2, hinge[1] + side * rz * w / 2, yaw

    mid = n // 2
    if n % 2:
        out[mid] = (0.0, -d, 0.0)
        right_edge, left_edge, first_right, first_left = (widths[mid] / 2, -d), (-widths[mid] / 2, -d), mid + 1, mid - 1
        yaw_r = yaw_l = 0.0
    else:  # a seam straight ahead
        right_edge, left_edge, first_right, first_left = (gap / 2, -d), (-gap / 2, -d), mid, mid - 1
        yaw_r = yaw_l = 0.0
    for i in range(first_right, n):  # to the right: screen i hangs from the previous right edge
        rx, rz = right(yaw_r)
        g = gap if i != first_right or n % 2 else 0
        hinge = (right_edge[0] + rx * g, right_edge[1] + rz * g)
        cx, cz, yaw_r = hang(hinge, widths[i], +1)
        out[i] = (cx, cz, yaw_r)
        rx, rz = right(yaw_r)
        right_edge = (cx + rx * widths[i] / 2, cz + rz * widths[i] / 2)
    for i in range(first_left, -1, -1):  # to the left, mirrored
        rx, rz = right(yaw_l)
        g = gap if i != first_left or n % 2 else 0
        hinge = (left_edge[0] - rx * g, left_edge[1] - rz * g)
        cx, cz, yaw_l = hang(hinge, widths[i], -1)
        out[i] = (cx, cz, yaw_l)
        rx, rz = right(yaw_l)
        left_edge = (cx - rx * widths[i] / 2, cz - rz * widths[i] / 2)
    return out


def plan(layout, count, panel_size=None):
    """Screen poses in the head frame: [{"pos": (x, y, z), "face": (yaw, pitch), "roll": deg}]."""
    sizes = [screen_size(layout, i, panel_size) for i in range(count)]
    rolls = [ROLL[screen_rotation(layout, i)] for i in range(count)]
    if layout.get("mode") == "custom" and len(layout.get("screens", [])) >= count and all(
            "pos" in s for s in layout["screens"][:count]):
        return [{"pos": tuple(s["pos"]), "face": tuple(s.get("face", yaw_pitch(s["pos"]))),
                 "roll": float(s.get("roll", rolls[i]))} for i, s in enumerate(layout["screens"][:count])]
    p = layout["preset"]
    rows = max(1, min(int(p.get("rows", 1)), count))
    cols = math.ceil(count / rows)
    d = max(0.3, float(p.get("distance", 2.0)))
    gap = max(0.0, float(p.get("gap", 0.05)))
    height = float(p.get("height", 0.0))
    flat = p.get("kind") == "flat"
    grid = [list(range(r * cols, min(count, (r + 1) * cols))) for r in range(rows)]
    out = [None] * count
    if flat:
        # One flat wall: rows of screens side by side, centred, facing forward.
        row_h = [max(sizes[i][1] for i in row) for row in grid]
        top = height + (sum(row_h) + gap * (rows - 1)) / 2
        for r, row in enumerate(grid):
            y = top - sum(row_h[:r]) - gap * r - row_h[r] / 2
            x = -(sum(sizes[i][0] for i in row) + gap * (len(row) - 1)) / 2
            for i in row:
                out[i] = {"pos": (x + sizes[i][0] / 2, y, -d), "face": (0.0, 0.0), "roll": rolls[i]}
                x += sizes[i][0] + gap
        return out
    # Curved: each row hinged edge to edge around you (see _chain); rows stacked by angle
    # (a row of height h at distance d spans 2 atan(h/2d)), each tilted to face you.
    span = lambda m: 2 * math.degrees(math.atan(m / 2 / d))
    row_h = [max(span(sizes[i][1]) for i in row) for row in grid]
    g = span(gap)
    top = math.degrees(math.atan(height / d)) + (sum(row_h) + g * (rows - 1)) / 2
    for r, row in enumerate(grid):
        pitch = top - sum(row_h[:r]) - g * r - row_h[r] / 2
        cp, sp = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
        for i, (x, z, yaw) in zip(row, _chain([sizes[i][0] for i in row], d, gap)):
            # Tilt the row about the eye's left-right axis: forward distance shrinks by cos,
            # height grows by sin.
            r_h = math.hypot(x, z)
            out[i] = {"pos": (x * cp, r_h * sp, z * cp), "face": (yaw, pitch), "roll": rolls[i]}
    return out


def relative_pose(center, x_axis, z_axis, eye, heading):
    """A screen's pose in the world -> custom layout entry (pos, face, roll) in the head frame."""
    rel = turn_yaw(tuple(c - e for c, e in zip(center, eye)), -heading)
    fyaw, fpitch = yaw_pitch(tuple(-c for c in z_axis))
    # Roll: the panel's right vector against an upright panel's right and up.
    right = normalize(cross((0.0, 1.0, 0.0), z_axis))
    up = cross(z_axis, right)
    roll = math.degrees(math.atan2(dot(x_axis, up), dot(x_axis, right)))
    return {"pos": [round(v, 4) for v in rel], "face": [round(fyaw - heading, 2), round(fpitch, 2)],
            "roll": round(roll, 2)}


class Socket:
    """Request/reply over an abstract datagram socket (ft-screens or the pointer helper)."""

    def __init__(self, address, what):
        self.address, self.what = address, what
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.sock.bind("")  # autobind: an abstract address the other side can reply to

    def ask(self, text, timeout=10.0):
        self.sock.settimeout(timeout)
        try:
            self.sock.sendto(text.encode(), self.address)
            reply = self.sock.recv(8192).decode()
        except (OSError, socket.timeout) as e:
            raise RuntimeError(f"{self.what} didn't answer ({e})")
        if not reply.startswith("ok"):
            raise RuntimeError(reply)
        return reply


# ---------------------------------------------------------------- ft-screens

def screens_socket():
    return Socket(SCREENS, "ft-screens (the desktop's compositor) isn't running or")


def screen_args(layout=None):
    layout = layout or load_layout()
    return " ".join(f"--screen {w}x{h}@{screen_metres(layout, i):.3f}"
                    for i, (w, h) in ((i, screen_pixels(layout, i)) for i in range(screen_count(layout))))


def visibility(layout):
    v = dict(VISIBILITY)
    v.update(layout.get("visibility", {}))
    return v


def send_visibility(sock, layout):
    v = visibility(layout)
    sock.ask(f"visibility {v['mode']}")
    sock.ask(f"wrist {float(v['wrist_angle']):.1f}")
    sock.ask(f"gesture {v['gesture_hand']} {float(v['gesture_angle']):.1f}")
    sock.ask(f"controllers {v['controllers']}")
    sock.ask(f"ingames {v['in_games']}")


def parse_get(reply):
    """ft-screens' "get": pose, size, curve, active/idle opacity, anchor, device->screen rel.

    Formats (after the 15 pose/size/curve floats):
      iteration 3+: active idle anchor [rel...]
      iteration 2:  opacity anchor [rel...]
      older:        anchor [rel...]
    """
    f = reply.split()[1:]
    g = list(map(float, f[:15]))
    opacity = DEFAULT_OPACITY
    idle = DEFAULT_OPACITY
    anchor = "none"
    rel_start = 16
    if len(f) > 15:
        try:
            opacity = float(f[15])
            idle = opacity
            if len(f) > 16:
                try:
                    idle = float(f[16])
                    anchor = f[17] if len(f) > 17 else "none"
                    rel_start = 18
                except ValueError:
                    anchor = f[16]
                    rel_start = 17
        except ValueError:
            anchor = f[15]
            rel_start = 16
    out = {"center": tuple(g[0:3]), "x": tuple(g[3:6]), "y": tuple(g[6:9]), "z": tuple(g[9:12]),
           "metres": g[12], "height": g[13], "curve": g[14], "opacity": opacity,
           "active_opacity": opacity, "idle_opacity": idle,
           "anchor": normalize_anchor(anchor) or "world", "hand": anchor}
    if out["anchor"] != "world" and len(f) >= rel_start + 12:
        out["rel"] = [round(float(v), 5) for v in f[rel_start:rel_start + 12]]
    return out


def screens_up(sock):
    """How many screens ft-screens has shown so far."""
    f = sock.ask("screens").split()
    return sum(1 for s in f[2:] if not s.split(":")[1].startswith("0x"))


def ease_in_out(t):
    """Smoothstep-ish ease: 0..1 -> 0..1."""
    t = max(0.0, min(1.0, t))
    return 0.5 * (1.0 - math.cos(math.pi * t))


def angle_lerp(a, b, t):
    """Shortest-path lerp for degrees (359 -> 1 travels +2, not -358)."""
    d = (b - a + 180.0) % 360.0 - 180.0
    return a + d * t


def vec_lerp(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def apply_pin(sock, index, pin):
    anchor = pin_anchor(pin)
    if not anchor or anchor == "world" or len(pin.get("rel", [])) != 12:
        try:
            sock.ask(f"unpin {index}")
        except RuntimeError:
            pass
        return
    try:
        sock.ask(f"pin {index} {anchor} " + " ".join(f"{v:.5f}" for v in pin["rel"]))
    except RuntimeError as e:
        log(f"screen {index}: {e}")  # that device isn't tracked


def apply_opacity(sock, index, opacity, idle=None):
    try:
        active = float(opacity)
        idle_v = active if idle is None else float(idle)
        sock.ask(f"opacity {index} {active:.3f} {idle_v:.3f}")
    except RuntimeError as e:
        log(f"screen {index} opacity: {e}")


def apply_attention(sock, index, attention):
    att = screen_attention({"attention": attention} if isinstance(attention, dict) else {})
    try:
        if att["enabled"]:
            sock.ask(f"attention {index} on {att['in_ms']:.0f} {att['out_ms']:.0f} "
                     f"{att['dwell_ms']:.0f} {att['hold_ms']:.0f}")
        else:
            sock.ask(f"attention {index} off")
    except RuntimeError as e:
        log(f"screen {index} attention: {e}")


def apply_follow_deadzone(sock, index, deadzone):
    dz = screen_follow_deadzone({"follow_deadzone": deadzone} if isinstance(deadzone, dict) else {})
    try:
        if dz["enabled"]:
            sock.ask(f"deadzone {index} on {dz['degrees']:.1f} {dz['metres']:.3f}")
        else:
            sock.ask(f"deadzone {index} off")
    except RuntimeError as e:
        log(f"screen {index} deadzone: {e}")


def push_slot_state(sock=None):
    """Tell ft-screens which profile slots are filled and which is current (for chrome)."""
    if backend() != "screens":
        return
    store = load_profiles()
    slots = normalized_slots(store)
    current = 0
    cur_name = store.get("current")
    for i, name in enumerate(slots, 1):
        if name and name == cur_name:
            current = i
            break
    filled = ",".join(str(i) for i, n in enumerate(slots, 1) if n) or "-"
    cmd = f"slots-state {current} {filled}"
    try:
        (sock or screens_socket()).ask(cmd)
    except (RuntimeError, OSError, AttributeError):
        pass


def push_follow_lag(sock=None):
    try:
        ms = float(read_conf().get("FOLLOW_LAG_MS", str(DEFAULT_FOLLOW_LAG_MS)))
    except ValueError:
        ms = DEFAULT_FOLLOW_LAG_MS
    try:
        (sock or screens_socket()).ask(f"followlag {ms:.0f}")
    except RuntimeError:
        pass


def place_screen(sock, index, center, face, roll, metres, curve):
    sock.ask(f"width {index} {metres:.4f}")
    sock.ask(f"curve {index} {float(curve):.3f}")
    return sock.ask("place %d %.4f %.4f %.4f %.3f %.3f %.3f" % (index, *center, face[0], face[1], roll))


def live_screen_targets(sock, layout, count, eye, heading):
    """World-space place targets + pin info for the planned layout (for transitions)."""
    targets = []
    for i, t in enumerate(plan(layout, count)):
        world = turn_yaw(t["pos"], heading)
        center = tuple(e + v for e, v in zip(eye, world))
        entry = screen_entry(layout, i)
        pin = entry.get("pin") if layout.get("mode") == "custom" else None
        targets.append({
            "center": center,
            "face": (t["face"][0] + heading, t["face"][1]),
            "roll": t["roll"],
            "metres": screen_metres(layout, i),
            "curve": float(entry.get("curve", 0)),
            "opacity": screen_opacities(entry)[0],
            "idle_opacity": screen_opacities(entry)[1],
            "attention": screen_attention(entry),
            "follow_deadzone": screen_follow_deadzone(entry),
            "pin": pin if pin_anchor(pin) and pin_anchor(pin) != "world"
                         and len((pin or {}).get("rel", [])) == 12 else None,
        })
    return targets


def live_screen_state(sock, count):
    """Current live poses from ft-screens get (world absolute)."""
    out = []
    for i in range(count):
        g = parse_get(sock.ask(f"get {i + 1}"))
        # Recover facing from axes: -z is the panel front in ScreenPose export.
        fyaw, fpitch = yaw_pitch(tuple(-c for c in g["z"]))
        right = normalize(cross((0.0, 1.0, 0.0), g["z"]))
        up = cross(g["z"], right)
        roll = math.degrees(math.atan2(dot(g["x"], up), dot(g["x"], right)))
        pin = None
        if g["anchor"] != "world" and "rel" in g:
            pin = make_pin(g["anchor"], g["rel"])
        out.append({
            "center": g["center"], "face": (fyaw, fpitch), "roll": roll,
            "metres": g["metres"], "curve": g["curve"], "opacity": g.get("opacity", DEFAULT_OPACITY),
            "pin": pin,
        })
    return out


def transition_screens(sock, starts, targets, duration_ms):
    """Interpolate place/width/curve over duration_ms. Cross-anchor pins snap at the end."""
    n = len(targets)
    # Animate in world; drop pins for the duration so place commands stick.
    for i in range(n):
        try:
            sock.ask(f"unpin {i + 1}")
        except RuntimeError:
            pass
    duration = max(0.0, duration_ms) / 1000.0
    if duration <= 0:
        for i, t in enumerate(targets):
            place_screen(sock, i + 1, t["center"], t["face"], t["roll"], t["metres"], t["curve"])
            if t["pin"]:
                apply_pin(sock, i + 1, t["pin"])
            apply_opacity(sock, i + 1, t.get("opacity", DEFAULT_OPACITY), t.get("idle_opacity"))
            apply_attention(sock, i + 1, t.get("attention"))
            apply_follow_deadzone(sock, i + 1, t.get("follow_deadzone"))
        return
    steps = max(2, int(duration * 30))  # ~30 Hz over the control socket
    t0 = time.time()
    for step in range(1, steps + 1):
        # Pace by wall clock so a slow socket still finishes near duration.
        elapsed = time.time() - t0
        u = ease_in_out(min(1.0, elapsed / duration if duration else 1.0))
        if step == steps:
            u = 1.0
        for i in range(n):
            a, b = starts[i], targets[i]
            place_screen(
                sock, i + 1,
                vec_lerp(a["center"], b["center"], u),
                (angle_lerp(a["face"][0], b["face"][0], u), angle_lerp(a["face"][1], b["face"][1], u)),
                angle_lerp(a["roll"], b["roll"], u),
                a["metres"] + (b["metres"] - a["metres"]) * u,
                a["curve"] + (b["curve"] - a["curve"]) * u,
            )
        if u >= 1.0:
            break
        # Sleep toward the next frame boundary.
        target_t = t0 + duration * step / steps
        delay = target_t - time.time()
        if delay > 0:
            time.sleep(delay)
    for i, t in enumerate(targets):
        if t["pin"]:
            apply_pin(sock, i + 1, t["pin"])
        apply_opacity(sock, i + 1, t.get("opacity", DEFAULT_OPACITY), t.get("idle_opacity"))
        if "attention" in t:
            apply_attention(sock, i + 1, t["attention"])
        apply_follow_deadzone(sock, i + 1, t.get("follow_deadzone"))


def apply_screens(wait=0, duration_ms=0):
    layout = load_layout()
    count = screen_count(layout)
    deadline = time.time() + wait
    while True:
        try:
            sock = screens_socket()
            if screens_up(sock) >= count or time.time() >= deadline:
                break
        except RuntimeError:
            if time.time() >= deadline:
                raise
        time.sleep(1)
    f = sock.ask("head").split()
    eye, heading = tuple(map(float, f[1:4])), float(f[4])
    send_visibility(sock, layout)
    push_follow_lag(sock)
    targets = live_screen_targets(sock, layout, count, eye, heading)
    if duration_ms > 0:
        starts = live_screen_state(sock, count)
        transition_screens(sock, starts, targets, duration_ms)
        results = ["ok"] * count
    else:
        results = []
        for i, t in enumerate(targets):
            results.append(place_screen(sock, i + 1, t["center"], t["face"], t["roll"], t["metres"], t["curve"]))
            if t["pin"]:
                apply_pin(sock, i + 1, t["pin"])
            apply_opacity(sock, i + 1, t.get("opacity", DEFAULT_OPACITY), t.get("idle_opacity"))
            apply_attention(sock, i + 1, t.get("attention"))
            apply_follow_deadzone(sock, i + 1, t.get("follow_deadzone"))
    push_slot_state(sock)
    apply_instruments(sock, layout)
    log(f"arranged {count} screen(s)" + (f" over {duration_ms} ms" if duration_ms else ""))
    return results


def apply_instruments(sock, layout=None):
    """Push Spatial Instruments from layout to ft-screens (instant; no transition yet)."""
    layout = layout or load_layout()
    if backend() != "screens":
        return
    try:
        sock = sock or screens_socket()
    except RuntimeError:
        return
    # Clear first so removed instruments disappear.
    try:
        sock.ask("instrument clear")
    except RuntimeError:
        pass
    f = sock.ask("head").split()
    eye = tuple(map(float, f[1:4]))
    heading = float(f[4])
    for inst in instruments_from_layout(layout):
        iid = inst["id"]
        try:
            if not inst["enabled"]:
                sock.ask(f"instrument disable {iid}")
                continue
            sock.ask(f"instrument enable {iid}")
            sock.ask(f"instrument width {iid} {float(inst['metres']):.4f}")
            active, idle = inst["active_opacity"], inst["idle_opacity"]
            sock.ask(f"instrument opacity {iid} {active:.3f} {idle:.3f}")
            att = inst.get("attention") or {}
            if att.get("enabled"):
                sock.ask(f"instrument attention {iid} on")
            else:
                sock.ask(f"instrument attention {iid} off")
            pin = inst.get("pin")
            anchor = pin_anchor(pin)
            if "pos" in inst and "face" in inst:
                pos = inst["pos"]
                face = inst["face"]
                roll = float(inst.get("roll", 0))
                world = turn_yaw(tuple(pos), heading)
                center = tuple(e + v for e, v in zip(eye, world))
                sock.ask("instrument place %s %.4f %.4f %.4f %.3f %.3f %.3f" % (
                    iid, center[0], center[1], center[2],
                    float(face[0]) + heading, float(face[1]) if len(face) > 1 else 0.0, roll))
            else:
                sock.ask(f"instrument recenter {iid}")
            if anchor and anchor != "world" and pin and len(pin.get("rel", [])) == 12:
                rel = " ".join(f"{float(v):.6f}" for v in pin["rel"])
                sock.ask(f"instrument pin {iid} {anchor} {rel}")
            else:
                sock.ask(f"instrument unpin {iid}")
        except RuntimeError as e:
            log(f"warning: instrument {iid}: {e}", file=sys.stderr)


def capture_screens():
    layout = load_layout()
    sock = screens_socket()
    f = sock.ask("head").split()
    eye, heading = tuple(map(float, f[1:4])), float(f[4])
    screens = []
    for i in range(screen_count(layout)):
        g = parse_get(sock.ask(f"get {i + 1}"))
        entry = dict(screen_entry(layout, i))
        entry.update(relative_pose(g["center"], g["x"], g["z"], eye, heading))
        entry["metres"] = round(g["metres"], 4)  # resized by hand
        entry["curve"] = round(g["curve"], 3)
        active = float(g.get("active_opacity", g.get("opacity", DEFAULT_OPACITY)))
        idle = float(g.get("idle_opacity", active))
        entry["opacity"] = round(active, 3)
        entry["active_opacity"] = round(active, 3)
        entry["idle_opacity"] = round(idle, 3)
        entry.pop("pin", None)
        if g.get("anchor") and g["anchor"] != "world" and "rel" in g:
            entry["pin"] = make_pin(g["anchor"], g["rel"])
        screens.append(entry)
    layout["screens"] = screens + layout.get("screens", [])[len(screens):]
    layout["mode"] = "custom"
    layout["instruments"] = capture_instruments(sock, eye, heading)
    save_layout(layout)
    return screens


def capture_instruments(sock, eye, heading):
    """Read live instrument state into layout entries."""
    out = []
    try:
        reply = sock.ask("instrument list")
    except RuntimeError:
        return instruments_from_layout(load_layout())
    # ok N id:type:enabled ...
    parts = reply.split()
    if not parts or parts[0] != "ok":
        return []
    for token in parts[2:]:
        bits = token.split(":")
        if len(bits) < 3:
            continue
        iid, itype, en = bits[0], bits[1], bits[2]
        try:
            g = parse_instrument_get(sock.ask(f"instrument get {iid}"))
        except RuntimeError:
            continue
        entry = {
            "id": iid,
            "type": itype,
            "enabled": en in ("1", "true", "on", "yes"),
            "metres": float(g.get("metres", DEFAULT_INSTRUMENT_METRES)),
            "active_opacity": float(g.get("active_opacity", g.get("opacity", 1.0))),
            "idle_opacity": float(g.get("idle_opacity", g.get("active_opacity", 1.0))),
        }
        entry["opacity"] = entry["active_opacity"]
        if "center" in g and "x" in g:
            entry.update(relative_pose(g["center"], g["x"], g["z"], eye, heading))
            entry["roll"] = float(g.get("roll", 0))
        if g.get("anchor") and g["anchor"] != "world" and "rel" in g:
            entry["pin"] = make_pin(g["anchor"], g["rel"])
        if g.get("attention"):
            entry["attention"] = {"enabled": True}
        else:
            entry["attention"] = {"enabled": False}
        inst = normalize_instrument(entry)
        if inst:
            out.append(inst)
    return out


def parse_instrument_get(reply):
    """Parse `instrument get` — same pose block as screen get, then metres active idle attention anchor [rel]."""
    f = reply.split()[1:]
    if len(f) < 18:
        raise RuntimeError(reply)
    g = list(map(float, f[:15]))
    out = {
        "center": tuple(g[0:3]),
        "x": tuple(g[3:6]),
        "y": tuple(g[6:9]),
        "z": tuple(g[9:12]),
        "metres": g[12],
        "height": g[13],
        "curve": g[14],
        "active_opacity": float(f[15]),
        "idle_opacity": float(f[16]),
        "opacity": float(f[15]),
        "attention": int(float(f[17])) != 0,
        "anchor": "world",
    }
    if len(f) > 18:
        out["anchor"] = normalize_anchor(f[18]) or "world"
    if out["anchor"] != "world" and len(f) >= 31:
        out["rel"] = [round(float(v), 5) for v in f[19:31]]
    return out


def instrument_cmd(argv):
    """ft-layout instrument list|state|enable|disable|recenter [id] [--json]."""
    if len(argv) < 3:
        print("usage: ft-layout instrument list|state|enable|disable|recenter [clock] [--json]",
              file=sys.stderr)
        return 2
    sub = argv[2]
    as_json = "--json" in argv
    args = [a for a in argv[3:] if a != "--json"]
    iid = args[0] if args else "clock"

    if sub in ("list", "state"):
        layout = load_layout()
        items = instruments_from_layout(layout)
        if as_json:
            print(json.dumps({"instruments": items}, separators=(",", ":")))
        else:
            if not items:
                print("(no instruments)")
            for inst in items:
                pin = pin_anchor(inst.get("pin")) or "world"
                print(f"{inst['id']}\ttype={inst['type']}\tenabled={int(inst['enabled'])}\t"
                      f"anchor={pin}\tmetres={inst['metres']}\t"
                      f"active={inst['active_opacity']}\tidle={inst['idle_opacity']}\t"
                      f"attention={int(bool((inst.get('attention') or {}).get('enabled')))}")
        return 0

    if sub in ("enable", "disable", "recenter"):
        layout = load_layout()
        inst = instrument_entry(layout, iid) or default_clock_instrument()
        if inst["id"] != iid:
            inst["id"] = iid
        if sub == "enable":
            inst["enabled"] = True
        elif sub == "disable":
            inst["enabled"] = False
        layout = upsert_instrument(layout, inst)
        save_layout(layout)
        if backend() == "screens":
            sock = screens_socket()
            if sub == "enable":
                sock.ask(f"instrument enable {iid}")
                if "pos" not in inst:
                    sock.ask(f"instrument recenter {iid}")
                apply_instruments(sock, layout)
            elif sub == "disable":
                sock.ask(f"instrument disable {iid}")
            else:
                sock.ask(f"instrument enable {iid}")
                sock.ask(f"instrument recenter {iid}")
                # Persist new pose
                f = sock.ask("head").split()
                eye, heading = tuple(map(float, f[1:4])), float(f[4])
                layout["instruments"] = capture_instruments(sock, eye, heading)
                # Keep enabled true after recenter
                for e in layout["instruments"]:
                    if e["id"] == iid:
                        e["enabled"] = True
                save_layout(layout)
        log(f"instrument {iid}: {sub}")
        return 0

    print(f"unknown instrument command {sub!r}", file=sys.stderr)
    return 2


# ---------------------------------------------------------------- gamescope (dashboard panels)

def vrcmd(*args, timeout=10):
    env = dict(os.environ, LD_LIBRARY_PATH=os.path.dirname(VRCMD))
    try:
        return subprocess.run([VRCMD, *args], capture_output=True, text=True, timeout=timeout, env=env).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def screen_keys():
    """The screens' overlay keys, in window order. gamescope (PerWindow) names each
    window's overlay frametop.app.<window seq>; .app.0 is its default connector, which
    never gets a window. It must be skipped: docking an unknown key moves whatever
    panel the dashboard shows instead."""
    keys = []
    for m in re.finditer(r"^'(frametop\.app\.(\d+))' .*VROverlayType_Dashboard_Main", vrcmd("--overlays"), re.M):
        if int(m.group(2)) > 0:
            keys.append((int(m.group(2)), m.group(1)))
    return [k for _, k in sorted(keys)]


def visible_keys():
    return set(re.findall(r"^'([^']+)' .* visible VROverlayType", vrcmd("--overlays"), re.M))


def helper_measure(helper, key):
    f = list(map(float, helper.ask(f"measure {key}").split()[1:]))
    return {"center": tuple(f[0:3]), "size": (f[3], f[4]), "x": tuple(f[5:8]), "y": tuple(f[8:11]),
            "z": tuple(f[11:14])}


def float_screen(key):
    """Float a docked screen: dock it into the dashboard (which opens the dashboard; a
    floated panel takes its first position from it, and none exists while it's closed),
    float it, then close the dashboard (so the carry can't snap it back in). A new
    window starts docked in the dashboard, where a dashboard request is ignored as
    redundant (and doesn't open the dashboard), so it goes to theater first."""
    vrcmd("--dock-overlay", "theater", key)
    time.sleep(0.5)
    vrcmd("--dock-overlay", "dashboard", key)
    time.sleep(0.8)
    vrcmd("--dock-overlay", "world", key)
    time.sleep(0.8)
    vrcmd("--hidedashboard")
    time.sleep(0.8)


def apply_gamescope(wait=0):
    layout = load_layout()
    count = screen_count(layout)
    deadline = time.time() + wait
    keys = screen_keys()
    while len(keys) < count and time.time() < deadline:
        time.sleep(1)
        keys = screen_keys()
    if wait:
        time.sleep(3)  # let Plasma draw before the screens start moving
    if not keys:
        raise RuntimeError("no Frametop screens in SteamVR; is the desktop running?")
    keys = keys[:count]
    helper = Socket(HELPER, "the pointer helper (frametop-pointer.service)")
    f = helper.ask("head").split()
    eye, heading = tuple(map(float, f[1:4])), float(f[4])
    vrcmd("--hidedashboard")
    time.sleep(0.5)
    shown = visible_keys()
    size = None
    for key in keys:
        if key not in shown:
            float_screen(key)
        try:
            m = helper_measure(helper, key)
        except RuntimeError:
            float_screen(key)  # floating but without a position: float it again
            m = helper_measure(helper, key)
        # The landscape size: a screen's panel is always landscape before it's rolled.
        size = size or (tuple(sorted(m["size"], reverse=True)))
    results = []
    for key, t in zip(keys, plan(layout, len(keys), size)):
        center = tuple(e + v for e, v in zip(eye, turn_yaw(t["pos"], heading)))
        reply = helper.ask("place %s %.4f %.4f %.4f %.3f %.3f %.3f" % (key, *center, t["face"][0] + heading,
                                                                        t["face"][1], t["roll"]), timeout=30)
        log(reply)
        results.append(reply)
    if size and list(size) != layout.get("panel_size"):
        layout["panel_size"] = [round(size[0], 4), round(size[1], 4)]
        save_layout(layout)
    return results


def capture_gamescope():
    layout = load_layout()
    helper = Socket(HELPER, "the pointer helper (frametop-pointer.service)")
    f = helper.ask("head").split()
    eye, heading = tuple(map(float, f[1:4])), float(f[4])
    shown = visible_keys()
    keys = [k for k in screen_keys() if k in shown]
    if not keys:
        raise RuntimeError("no floating screens to capture (screens docked in the dashboard don't count)")
    screens = []
    for i, key in enumerate(keys):
        m = helper_measure(helper, key)
        entry = dict(screen_entry(layout, i))
        entry.update(relative_pose(m["center"], m["x"], m["z"], eye, heading))
        screens.append(entry)
        layout["panel_size"] = [round(v, 4) for v in sorted(m["size"], reverse=True)]
    layout["screens"] = screens + layout.get("screens", [])[len(screens):]
    layout["mode"] = "custom"
    save_layout(layout)
    return screens


def apply(wait=0, duration_ms=0):
    if backend() == "screens":
        return apply_screens(wait, duration_ms=duration_ms)
    if duration_ms:
        log("warning: --duration is only supported with the screens backend; applying instantly", file=sys.stderr)
    return apply_gamescope(wait)


def capture():
    return capture_screens() if backend() == "screens" else capture_gamescope()


# ---------------------------------------------------------------- named spatial profiles

def load_profiles():
    """Load profiles file. Missing/corrupt -> empty store; never touches the active layout."""
    empty = {"current": None, "profiles": {}, "slots": [None] * SLOT_COUNT}
    try:
        with open(PROFILES_PATH) as f:
            data = json.load(f)
    except FileNotFoundError:
        return empty
    except (OSError, ValueError) as e:
        log(f"warning: profiles file unreadable ({e}); treating as empty", file=sys.stderr)
        return empty
    if not isinstance(data, dict):
        log("warning: profiles file malformed; treating as empty", file=sys.stderr)
        return empty
    profiles = data.get("profiles")
    if not isinstance(profiles, dict):
        profiles = {}
    current = data.get("current")
    if current is not None and current not in profiles:
        current = None
    store = {"current": current, "profiles": profiles, "slots": data.get("slots")}
    store["slots"] = normalized_slots(store)
    return store


def save_profiles(store):
    out = {
        "current": store.get("current"),
        "profiles": store.get("profiles") or {},
        "slots": normalized_slots(store),
    }
    atomic_write_json(PROFILES_PATH, out)


def normalized_slots(store):
    """Always SLOT_COUNT entries; unknown/missing profile names become None."""
    raw = store.get("slots") if isinstance(store, dict) else None
    profiles = (store.get("profiles") or {}) if isinstance(store, dict) else {}
    out = [None] * SLOT_COUNT
    if isinstance(raw, list):
        for i in range(min(SLOT_COUNT, len(raw))):
            name = raw[i]
            if isinstance(name, str) and name in profiles:
                out[i] = name
            elif name in (None, "", "-"):
                out[i] = None
    return out


def profile_from_layout(layout):
    """Spatial snapshot for the configured screen count (+ instruments)."""
    count = screen_count(layout)
    screens = [spatial_screen(screen_entry(layout, i)) for i in range(count)]
    instruments = []
    for entry in instruments_from_layout(layout):
        snap = spatial_instrument(entry)
        if snap:
            instruments.append(snap)
    return {"screens": screens, "instruments": instruments}


def merge_profile_into_layout(layout, profile):
    """Apply spatial fields onto the active layout; leave size/scale/primary/visibility alone."""
    layout = json.loads(json.dumps(layout))  # deep copy
    screens = layout.setdefault("screens", [])
    count = screen_count(layout)
    src = profile.get("screens") or []
    if len(src) != count:
        raise RuntimeError(f"profile has {len(src)} screen(s); active layout has {count} "
                           "(profiles assume a fixed screen count)")
    while len(screens) < count:
        screens.append({"size": [1920, 1080], "metres": 1920 / PIXELS_PER_METRE})
    for i in range(count):
        entry = dict(screens[i])
        spatial = src[i] or {}
        for k in ("pos", "face", "roll", "metres", "curve", "opacity", "active_opacity", "idle_opacity"):
            if k in spatial:
                entry[k] = spatial[k]
        active, idle = screen_opacities(spatial if spatial else entry)
        entry["opacity"] = round(active, 3)
        entry["active_opacity"] = round(active, 3)
        entry["idle_opacity"] = round(idle, 3)
        entry.pop("pin", None)
        pin = spatial.get("pin")
        if pin_anchor(pin) and pin_anchor(pin) != "world" and len((pin or {}).get("rel", [])) == 12:
            entry["pin"] = make_pin(pin_anchor(pin), pin["rel"])
        if "attention" in spatial and isinstance(spatial["attention"], dict):
            entry["attention"] = screen_attention(spatial)
        else:
            entry.pop("attention", None)
        if "follow_deadzone" in spatial and isinstance(spatial["follow_deadzone"], dict):
            entry["follow_deadzone"] = screen_follow_deadzone(spatial)
        else:
            entry.pop("follow_deadzone", None)
        screens[i] = entry
    layout["screens"] = screens
    layout["mode"] = "custom"
    # Missing instruments key => no instruments (old profiles).
    if "instruments" not in profile:
        layout["instruments"] = []
    else:
        layout["instruments"] = [
            x for x in (normalize_instrument(e) for e in (profile.get("instruments") or [])) if x
        ]
    return layout


def resolve_duration(argv, default=DEFAULT_PROFILE_DURATION_MS):
    """--duration MS overrides; absent => default (450). Explicit 0 = instant."""
    if "--duration" in argv:
        return float(argv[argv.index("--duration") + 1])
    return float(default)


def profile_list(as_json=False):
    store = load_profiles()
    names = sorted(store["profiles"])
    if as_json:
        print(json.dumps({"current": store["current"], "profiles": names,
                          "slots": store["slots"]}, separators=(",", ":")))
    else:
        for name in names:
            mark = " *" if name == store["current"] else ""
            print(f"{name}{mark}")
    return 0


def profile_current(as_json=False):
    store = load_profiles()
    name = store["current"]
    if as_json:
        print(json.dumps({"current": name}, separators=(",", ":")))
    else:
        print(name or "")
    return 0


def profile_save(name):
    if not name or name.startswith("-"):
        raise RuntimeError("profile name required")
    # Capture live arrangement first so the profile matches what you see.
    if backend() == "screens":
        capture_screens()
    else:
        capture_gamescope()
    layout = load_layout()
    store = load_profiles()
    store["profiles"][name] = profile_from_layout(layout)
    store["current"] = name
    save_profiles(store)
    push_slot_state()
    log(f"saved profile {name!r} ({len(store['profiles'][name]['screens'])} screen(s))", file=sys.stderr)
    return 0


def profile_apply(name, duration_ms=None):
    if duration_ms is None:
        duration_ms = DEFAULT_PROFILE_DURATION_MS
    store = load_profiles()
    if name not in store["profiles"]:
        raise RuntimeError(f"no profile named {name!r}")
    layout = merge_profile_into_layout(load_layout(), store["profiles"][name])
    save_layout(layout)
    store["current"] = name
    save_profiles(store)
    apply(duration_ms=duration_ms)
    log(f"applied profile {name!r}", file=sys.stderr)
    return 0


def profile_delete(name):
    store = load_profiles()
    if name not in store["profiles"]:
        raise RuntimeError(f"no profile named {name!r}")
    del store["profiles"][name]
    if store["current"] == name:
        store["current"] = None
    slots = normalized_slots(store)
    store["slots"] = [None if s == name else s for s in slots]
    save_profiles(store)
    push_slot_state()
    log(f"deleted profile {name!r}", file=sys.stderr)
    return 0


def profile_slot(slot, name):
    slot = int(slot)
    if not 1 <= slot <= SLOT_COUNT:
        raise RuntimeError(f"slot must be 1..{SLOT_COUNT}")
    store = load_profiles()
    if name not in store["profiles"]:
        raise RuntimeError(f"no profile named {name!r}")
    slots = normalized_slots(store)
    slots[slot - 1] = name
    store["slots"] = slots
    save_profiles(store)
    push_slot_state()
    log(f"slot {slot} -> {name!r}", file=sys.stderr)
    return 0


def profile_unslot(slot):
    slot = int(slot)
    if not 1 <= slot <= SLOT_COUNT:
        raise RuntimeError(f"slot must be 1..{SLOT_COUNT}")
    store = load_profiles()
    slots = normalized_slots(store)
    slots[slot - 1] = None
    store["slots"] = slots
    save_profiles(store)
    push_slot_state()
    log(f"slot {slot} cleared", file=sys.stderr)
    return 0


def profile_slots(as_json=False):
    store = load_profiles()
    slots = normalized_slots(store)
    current_slot = 0
    for i, name in enumerate(slots, 1):
        if name and name == store.get("current"):
            current_slot = i
            break
    if as_json:
        print(json.dumps({"slots": [{"index": i, "profile": n} for i, n in enumerate(slots, 1)],
                          "current": store.get("current"), "current_slot": current_slot},
                         separators=(",", ":")))
    else:
        for i, name in enumerate(slots, 1):
            mark = " *" if i == current_slot else ""
            print(f"{i}: {name or '-'}{mark}")
    return 0


def profile_apply_slot(slot, duration_ms=None):
    slot = int(slot)
    if not 1 <= slot <= SLOT_COUNT:
        raise RuntimeError(f"slot must be 1..{SLOT_COUNT}")
    store = load_profiles()
    name = normalized_slots(store)[slot - 1]
    if not name:
        raise RuntimeError(f"slot {slot} is empty")
    return profile_apply(name, duration_ms=duration_ms)


def profile_step(delta, duration_ms=None):
    """Next/previous among filled slots, wrapping."""
    store = load_profiles()
    slots = normalized_slots(store)
    filled = [i for i, n in enumerate(slots, 1) if n]
    if not filled:
        raise RuntimeError("no profiles assigned to slots")
    cur = 0
    for i, name in enumerate(slots, 1):
        if name and name == store.get("current"):
            cur = i
            break
    if cur in filled:
        idx = filled.index(cur)
        nxt = filled[(idx + delta) % len(filled)]
    else:
        nxt = filled[0 if delta >= 0 else -1]
    return profile_apply_slot(nxt, duration_ms=duration_ms)


def screen_state_json():
    """Machine-readable per-screen state for Quickshell / debugging."""
    layout = load_layout()
    store = load_profiles()
    slots = normalized_slots(store)
    current_slot = 0
    for i, name in enumerate(slots, 1):
        if name and name == store.get("current"):
            current_slot = i
            break
    screens = []
    live = None
    if backend() == "screens":
        try:
            sock = screens_socket()
            live = [parse_get(sock.ask(f"get {i + 1}")) for i in range(screen_count(layout))]
        except RuntimeError:
            live = None
    for i in range(screen_count(layout)):
        entry = screen_entry(layout, i)
        pin = entry.get("pin")
        active, idle = screen_opacities(entry)
        row = {
            "index": i + 1,
            "anchor": pin_anchor(pin) or "world",
            "opacity": active,
            "active_opacity": active,
            "idle_opacity": idle,
            "attention": screen_attention(entry),
            "metres": screen_metres(layout, i),
            "curve": float(entry.get("curve", 0)),
        }
        if live and i < len(live):
            row["live_anchor"] = live[i].get("anchor", "world")
            row["live_opacity"] = live[i].get("opacity", DEFAULT_OPACITY)
            row["live_active_opacity"] = live[i].get("active_opacity", row["live_opacity"])
            row["live_idle_opacity"] = live[i].get("idle_opacity", row["live_opacity"])
        screens.append(row)
    gaze = None
    if backend() == "screens":
        try:
            gaze = screens_socket().ask("gaze state")
        except RuntimeError:
            gaze = None
    print(json.dumps({
        "current_profile": store.get("current"),
        "current_slot": current_slot,
        "slots": slots,
        "follow_lag_ms": float(read_conf().get("FOLLOW_LAG_MS", DEFAULT_FOLLOW_LAG_MS)),
        "gaze": gaze,
        "screens": screens,
    }, separators=(",", ":")))
    return 0


def gaze_cmd(argv):
    """ft-layout gaze state|debug on|off|fallback head|fallback off — proxy to ft-screens."""
    if len(argv) < 3:
        print("usage: ft-layout gaze state|debug on|off|fallback head|fallback off", file=sys.stderr)
        return 2
    reply = screens_socket().ask("gaze " + " ".join(argv[2:]))
    # Machine-readable on stdout for `state`; debug toggles go to log (stderr-ish via log).
    if argv[2] == "state":
        print(reply)
    else:
        log(reply)
    return 0


# ---------------------------------------------------------------- Semantic actions
# One name → one implementation. VR chrome, input-relay button maps, Display Settings,
# Quickshell, and future gestures should call these instead of re-encoding CLI argv.

# Canonical dotted names (preferred for new callers / Quickshell).
SEMANTIC_ACTIONS = tuple(
    [f"profile.slot.{i}" for i in range(1, SLOT_COUNT + 1)]
    + ["profile.next", "profile.previous", "layout.reset", "screens.toggle"]
)

# Input Settings / button-map aliases → canonical names (kept for existing bindings).
ACTION_ALIASES = {
    "profile_slot_1": "profile.slot.1",
    "profile_slot_2": "profile.slot.2",
    "profile_slot_3": "profile.slot.3",
    "profile_slot_4": "profile.slot.4",
    "profile_slot_5": "profile.slot.5",
    "profile_slot_6": "profile.slot.6",
    "profile_next": "profile.next",
    "profile_previous": "profile.previous",
    "layout_reset": "layout.reset",
    "screens_toggle": "screens.toggle",
}

ACTION_LABELS = {
    "profile.slot.1": "Apply profile slot 1",
    "profile.slot.2": "Apply profile slot 2",
    "profile.slot.3": "Apply profile slot 3",
    "profile.slot.4": "Apply profile slot 4",
    "profile.slot.5": "Apply profile slot 5",
    "profile.slot.6": "Apply profile slot 6",
    "profile.next": "Next profile slot",
    "profile.previous": "Previous profile slot",
    "layout.reset": "Reset desktop screen layout",
    "screens.toggle": "Hide/show desktop screens",
}


def normalize_action(name):
    """Map an alias or canonical name to a canonical semantic action, or None."""
    if not name:
        return None
    name = str(name).strip()
    if name in ACTION_ALIASES:
        return ACTION_ALIASES[name]
    if name in SEMANTIC_ACTIONS:
        return name
    return None


def list_actions(as_json=False):
    rows = [{"name": n, "label": ACTION_LABELS.get(n, n),
             "aliases": sorted(a for a, c in ACTION_ALIASES.items() if c == n)}
            for n in SEMANTIC_ACTIONS]
    if as_json:
        print(json.dumps({"actions": rows}, separators=(",", ":")))
    else:
        for r in rows:
            alias = f"  (aliases: {', '.join(r['aliases'])})" if r["aliases"] else ""
            print(f"{r['name']}: {r['label']}{alias}")
    return 0


def run_action(name, duration_ms=None):
    """Execute a semantic action. Raises RuntimeError on unknown names / apply failures."""
    canonical = normalize_action(name)
    if not canonical:
        known = ", ".join(SEMANTIC_ACTIONS)
        raise RuntimeError(f"unknown action {name!r}; try: {known}")
    if canonical.startswith("profile.slot."):
        slot = int(canonical.rsplit(".", 1)[1])
        return profile_apply_slot(slot, duration_ms=duration_ms)
    if canonical == "profile.next":
        return profile_step(1, duration_ms=duration_ms)
    if canonical == "profile.previous":
        return profile_step(-1, duration_ms=duration_ms)
    if canonical == "layout.reset":
        apply(duration_ms=0 if duration_ms is None else duration_ms)
        return 0
    if canonical == "screens.toggle":
        log(screens_socket().ask("toggle"))
        return 0
    raise RuntimeError(f"unhandled action {canonical!r}")


# ---------------------------------------------------------------- KWin (scale, positions, primary)

def nested_env():
    """Environment of the running Frametop Plasma session (its private bus and runtime dir)."""
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/comm") as f:
                if f.read().strip() != "plasmashell":
                    continue
            with open(f"/proc/{pid}/environ", "rb") as f:
                env = dict(e.split("=", 1) for e in f.read().decode(errors="replace").split("\0") if "=" in e)
        except OSError:
            continue
        if env.get("XDG_RUNTIME_DIR", "").endswith("/frametop"):
            keep = ("DBUS_SESSION_BUS_ADDRESS", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "XDG_CONFIG_HOME")
            return dict(os.environ, **{k: env[k] for k in keep if k in env})
    return None


def outputs(env):
    """KWin's outputs, in screen order (WL-0, WL-1, ...)."""
    try:
        data = json.loads(subprocess.run(["kscreen-doctor", "-j"], capture_output=True, text=True, env=env,
                                         timeout=10).stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []
    outs = [o for o in data.get("outputs", []) if o.get("connected")]
    return sorted(outs, key=lambda o: [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", o.get("name", ""))])


KSCREEN_ROTATION = {1: "normal", 2: "left", 4: "inverted", 8: "right"}  # kscreen-doctor -j "rotation"


def apply_scales():
    """Per-screen scale and rotation, positions side by side, and the primary screen (the
    taskbar goes there) to KWin, which keeps them in the session's config."""
    env = nested_env()
    if not env:
        raise RuntimeError("the Frametop desktop isn't running")
    layout = load_layout()
    args = []
    outs = outputs(env)
    for i, o in enumerate(outs):
        s = screen_scale(layout, i)
        if abs(float(o.get("scale", 1)) - s) > 1e-3:
            args.append(f"output.{o['id']}.scale.{s:g}")
        rot = screen_rotation(layout, i)
        if KSCREEN_ROTATION.get(o.get("rotation"), "normal") != rot:
            args.append(f"output.{o['id']}.rotation.{rot}")
    if outs:
        p = outs[min(primary_screen(layout), len(outs) - 1)]
        if p.get("priority") != 1:
            args.append(f"output.{p['id']}.priority.1")
    if args:
        subprocess.run(["kscreen-doctor", *args], capture_output=True, env=env, timeout=20)
    # Side by side in screen order, centred vertically, so the pointer and dragged windows
    # cross between neighbours.
    outs = outputs(env)
    # kscreen's "size" is in pixels (already turned for a rotation); positions are in
    # logical units, the pixels divided by the scale (KWin rounds up).
    sizes = [(math.ceil(o["size"]["width"] / float(o.get("scale", 1)) - 1e-6),
              math.ceil(o["size"]["height"] / float(o.get("scale", 1)) - 1e-6))
             for o in outs if o.get("size")]
    if len(sizes) == len(outs) and outs:
        tallest, x, moves = max(h for _, h in sizes), 0, []
        for o, (w, h) in zip(outs, sizes):
            want = (x, (tallest - h) // 2)
            if (o.get("pos", {}).get("x"), o.get("pos", {}).get("y")) != want:
                moves.append(f"output.{o['id']}.position.{want[0]},{want[1]}")
            x += w
        if moves:
            subprocess.run(["kscreen-doctor", *moves], capture_output=True, env=env, timeout=20)
            args += moves
    # Tell ft-screens each output scale so laser→seat mapping can correct wl dpr ≠ scale.
    try:
        sock = screens_socket()
        for i in range(len(outs) or screen_count(layout)):
            s = screen_scale(layout, i)
            try:
                sock.ask(f"scale {i + 1} {s:g}")
            except RuntimeError:
                pass
    except RuntimeError:
        pass
    return args


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__.split("Usage")[1].split("\n", 1)[1])
        return 0 if len(argv) >= 2 else 2
    cmd = argv[1]
    try:
        if cmd == "plan":
            layout = load_layout()
            print(json.dumps(plan(layout, screen_count(layout))))
        elif cmd == "screen-args":
            print(screen_args())
        elif cmd == "toggle":
            log(screens_socket().ask("toggle"))
        elif cmd in ("pin", "unpin") and len(argv) >= 3:
            log(screens_socket().ask(" ".join(argv[1:])))
        elif cmd == "opacity" and len(argv) >= 4:
            # Recovery / live tweak: ft-layout opacity N ACTIVE [IDLE]
            index = int(argv[2])
            active = float(argv[3])
            idle = float(argv[4]) if len(argv) >= 5 else active
            layout = load_layout()
            entry = dict(screen_entry(layout, index - 1))
            entry["opacity"] = round(active, 3)
            entry["active_opacity"] = round(active, 3)
            entry["idle_opacity"] = round(idle, 3)
            # Soft-lock escape: clear attention so idle=0 cannot hide the screen again.
            entry.pop("attention", None)
            screens = list(layout.get("screens") or [])
            while len(screens) < index:
                screens.append({})
            screens[index - 1] = entry
            layout["screens"] = screens
            save_layout(layout)
            if backend() == "screens":
                sock = screens_socket()
                apply_opacity(sock, index, active, idle)
                apply_attention(sock, index, {"enabled": False})
            log(f"screen {index}: opacity active={active:.3f} idle={idle:.3f} (attention off)")
        elif cmd == "screen" and len(argv) >= 3 and argv[2] == "state":
            return screen_state_json()
        elif cmd == "gaze":
            return gaze_cmd(argv)
        elif cmd == "instrument":
            return instrument_cmd(argv)
        elif cmd == "action":
            if len(argv) < 3:
                print("usage: ft-layout action NAME|--list [--json] [--duration MS]", file=sys.stderr)
                return 2
            if argv[2] in ("list", "--list"):
                return list_actions(as_json="--json" in argv)
            name = argv[2]

            def locked_action():
                with open(LOCK_PATH, "w") as lock:
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        log("another ft-layout is already running", file=sys.stderr)
                        return 1
                    return run_action(name, duration_ms=resolve_duration(argv))

            # Instant actions should not block behind a layout lock.
            if normalize_action(name) in ("screens.toggle",):
                return run_action(name)
            return locked_action()
        elif cmd == "profile":
            if len(argv) < 3:
                print("usage: ft-layout profile list|current|save|apply|delete|slot|unslot|slots|"
                      "apply-slot|next|previous ...", file=sys.stderr)
                return 2
            sub = argv[2]

            def locked(fn):
                with open(LOCK_PATH, "w") as lock:
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        log("another ft-layout is already running", file=sys.stderr)
                        return 1
                    return fn()

            if sub == "list":
                return profile_list(as_json="--json" in argv)
            if sub == "current":
                return profile_current(as_json="--json" in argv)
            if sub == "slots":
                return profile_slots(as_json="--json" in argv)
            if sub == "save" and len(argv) >= 4:
                return locked(lambda: profile_save(argv[3]))
            if sub == "apply" and len(argv) >= 4:
                return locked(lambda: profile_apply(argv[3], duration_ms=resolve_duration(argv)))
            if sub == "delete" and len(argv) >= 4:
                return profile_delete(argv[3])
            if sub == "slot" and len(argv) >= 5:
                return profile_slot(argv[3], argv[4])
            if sub == "unslot" and len(argv) >= 4:
                return profile_unslot(argv[3])
            if sub == "apply-slot" and len(argv) >= 4:
                return locked(lambda: profile_apply_slot(argv[3], duration_ms=resolve_duration(argv)))
            if sub == "next":
                return locked(lambda: profile_step(1, duration_ms=resolve_duration(argv)))
            if sub == "previous":
                return locked(lambda: profile_step(-1, duration_ms=resolve_duration(argv)))
            print(f"unknown profile command: {' '.join(argv[2:])}", file=sys.stderr)
            return 2
        elif cmd in ("apply", "capture", "scale"):
            with open(LOCK_PATH, "w") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    log("another ft-layout is already running", file=sys.stderr)
                    return 1
                if cmd == "apply":
                    wait = float(argv[argv.index("--wait") + 1]) if "--wait" in argv else 0
                    duration = float(argv[argv.index("--duration") + 1]) if "--duration" in argv else 0
                    if wait and not load_layout().get("auto", True):
                        log("auto-arrange is off")
                        if backend() == "screens":  # the visibility settings apply anyway
                            try:
                                sock = screens_socket()
                                deadline = time.time() + wait
                                while screens_up(sock) < screen_count() and time.time() < deadline:
                                    time.sleep(1)
                                send_visibility(sock, load_layout())
                            except RuntimeError as e:
                                log(f"visibility: {e}")
                    else:
                        apply(wait, duration_ms=duration)
                    if wait:
                        # KWin keeps these, but new screens or a changed layout need them once.
                        for _ in range(30):  # Plasma may still be starting
                            try:
                                log("kwin: " + (" ".join(apply_scales()) or "unchanged"))
                                break
                            except RuntimeError as e:
                                last = e
                                time.sleep(1)
                        else:
                            log(f"kwin: {last}")
                elif cmd == "capture":
                    for i, s in enumerate(capture()):
                        log(f"screen {i + 1}: {s}")
                else:
                    changes = apply_scales()
                    log("kwin: " + (" ".join(changes) if changes else "unchanged"))
        else:
            print(f"unknown command: {cmd}", file=sys.stderr)
            return 2
    except RuntimeError as e:
        log(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
