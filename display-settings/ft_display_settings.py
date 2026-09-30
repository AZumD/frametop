#!/usr/bin/env python3
"""Frametop Display Settings: the Frametop screens' count, resolution, size, scale, and layout.

A Kirigami (QML) app with a Python backend, like Frametop Input Settings. It runs in
the dev container:
  - Screens (ft-screens backend): each screen's resolution (any, portrait too), its width
    in VR in metres, its scale, and which one has the taskbar. Resolution and width
    apply at once (ft-screens' control socket, @ft_screens); adding or removing a screen
    when the desktop starts again. (gamescope backend: one shared resolution, at most
    1920x1080 worth of pixels, rotation for portrait.)
  - Visibility (ft-screens): when the screens show (always, only with the SteamVR
    dashboard open, while you look at a controller, or only when toggled), the wrist
    angle within which a pinned screen shows, and pin or unpin all screens.
  - Layout: a preset (curved or flat, rows, distance, gap, height) or the arrangement
    captured from where the screens are now, with a preview; arrange now; save the
    current arrangement; arrange automatically when the desktop starts.
Settings go to ~/.config/frametop.conf and ~/.config/frametop-layout.json. Anything
that touches SteamVR runs layout/ft-layout on the host.
Launch with display-settings/ft-display-settings (host wrapper).
"""
import os
import shutil
import socket
import sys

from PySide6.QtCore import Property, QObject, QProcess, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

HERE = os.path.dirname(os.path.abspath(__file__))
LAYOUT_DIR = os.path.join(HERE, "..", "layout")
sys.path.insert(0, LAYOUT_DIR)
import ft_layout  # noqa: E402  (pure Python: the same geometry ft-layout uses)

FT_LAYOUT = os.path.join(LAYOUT_DIR, "ft-layout")
DESKTOPS = os.path.join(HERE, "..", "desktops.sh")
CONF_PATH = ft_layout.CONF_PATH
FT_SCREENS = "\0ft_screens"
# gamescope's VR backend uploads a texture the size of a screen at start, through a
# 1920x1080x4-byte buffer: more pixels than 1920x1080 abort it (see the design notes).
MAX_PIXELS = 1920 * 1080
RESOLUTIONS = [(1280, 720), (1600, 900), (1920, 1080), (1728, 1080), (1920, 800), (2224, 928), (2560, 800)]
# ft-screens has no pixel limit; portrait screens are just tall.
SCREEN_RESOLUTIONS = [(1920, 1080, ""), (2560, 1440, ""), (3840, 2160, "4K"), (2560, 1080, "ultrawide"),
                      (3440, 1440, "ultrawide"), (5120, 1440, "super ultrawide"), (1920, 1200, "16:10"),
                      (2560, 1600, "16:10"), (1080, 1920, "portrait"), (1440, 2560, "portrait"),
                      (2160, 3840, "portrait 4K")]
SCALES = [0.75, 1.0, 1.25, 4 / 3, 1.5, 1.75, 2.0]
ROTATIONS = [("normal", "Landscape"), ("left", "Portrait"), ("right", "Portrait (flipped)")]


def write_conf_value(key, value):
    """Set KEY=value in frametop.conf, keeping comments and the rest of the file."""
    try:
        with open(CONF_PATH) as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []
    for i, line in enumerate(lines):
        if line.split("#", 1)[0].strip().startswith(f"{key}="):
            comment = line[line.index("#"):] if "#" in line else ""
            lines[i] = f"{key}={value}" + (f"   {comment}" if comment else "")
            break
    else:
        lines.append(f"{key}={value}")
    with open(CONF_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")


def host_command(*cmd):
    """argv to run a command on the SteamOS host (we live in the dev container).

    distrobox-host-exec reaches the host through the user's real session bus; inside the
    desktop our DBUS_SESSION_BUS_ADDRESS is the nested session's private one, where it
    fails (exit 127, silently)."""
    if not shutil.which("distrobox-host-exec"):
        return list(cmd)
    bus = f"unix:path=/run/user/{os.getuid()}/bus"
    return ["env", f"DBUS_SESSION_BUS_ADDRESS={bus}", "distrobox-host-exec"] + list(cmd)


class Backend(QObject):
    changed = Signal()
    busyChanged = Signal()
    message = Signal(str, bool)  # text, is error

    def __init__(self):
        super().__init__()
        self._busy = ""
        self._proc = None
        self._running = False
        self._running_count = 0
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self._sock.bind("")  # an abstract address ft-screens can reply to
        self._sock.settimeout(1.0)
        self._started = {}  # conf values the running desktop started with
        self.poll = QTimer(interval=3000, timeout=self._check_running)
        self.poll.start()
        self._check_running()

    # --- state ---
    def _conf(self):
        conf = ft_layout.read_conf()
        def num(key, default, cast=float):
            try:
                return cast(conf.get(key, default))
            except ValueError:
                return default
        return {"screens": num("SCREENS", 2, int), "width": num("WIDTH", 1920, int),
                "height": num("HEIGHT", 1080, int), "physWidth": num("PHYS_WIDTH", 1.6)}

    def _check_running(self):
        # The session's own Wayland socket (host processes' environments aren't readable
        # from the container, so ft_layout.nested_env() doesn't work here).
        running = os.path.exists(f"/run/user/{os.getuid()}/frametop/wayland-0")
        count = self._screens_running() if running and ft_layout.backend() == "screens" else 0
        if running != self._running or count != self._running_count:
            self._running = running
            self._running_count = count
            self._started = self._conf() if running else {}
            self.changed.emit()

    def _ask_screens(self, text):
        """Request/reply to ft-screens; None if it isn't running."""
        try:
            self._sock.sendto(text.encode(), FT_SCREENS)
            return self._sock.recv(4096).decode()
        except OSError:
            return None

    def _screens_running(self):
        reply = self._ask_screens("screens")
        return int(reply.split()[1]) if reply and reply.startswith("ok") else 0

    @Property(bool, notify=changed)
    def desktopRunning(self):
        return self._running

    @Property(str, notify=changed)
    def backend(self):
        return ft_layout.backend()

    @Property(bool, notify=changed)
    def restartNeeded(self):
        """ft-screens: screens added or removed since the desktop started; gamescope: count,
        resolution, or width changed."""
        if not self._running:
            return False
        if ft_layout.backend() == "screens":
            return self._running_count != ft_layout.screen_count(ft_layout.load_layout())
        return bool(self._started) and self._started != self._conf()

    @Property("QVariantList", constant=True)
    def screenResolutions(self):
        return [{"text": f"{w} × {h}" + (f"  ({t})" if t else ""), "width": w, "height": h}
                for w, h, t in SCREEN_RESOLUTIONS]

    @Property(int, notify=changed)
    def screens(self):
        return self._conf()["screens"]

    @Property(int, notify=changed)
    def width(self):
        return self._conf()["width"]

    @Property(int, notify=changed)
    def height(self):
        return self._conf()["height"]

    @Property(float, notify=changed)
    def physWidth(self):
        return self._conf()["physWidth"]

    @Property("QVariantList", constant=True)
    def resolutions(self):
        return [{"text": f"{w} × {h}", "width": w, "height": h} for w, h in RESOLUTIONS]

    @Property("QVariantList", constant=True)
    def scales(self):
        return [{"text": f"{round(s * 100)}%", "value": round(s, 4)} for s in SCALES]

    @Property("QVariantList", constant=True)
    def rotations(self):
        return [{"text": t, "value": v} for v, t in ROTATIONS]

    @Property("QVariantList", notify=changed)
    def screenList(self):
        c, layout = self._conf(), ft_layout.load_layout()
        out = []
        if ft_layout.backend() == "screens":
            primary = ft_layout.primary_screen(layout)
            for i in range(ft_layout.screen_count(layout)):
                w, h = ft_layout.screen_pixels(layout, i)
                s = ft_layout.screen_scale(layout, i)
                entry = ft_layout.screen_entry(layout, i)
                active, idle = ft_layout.screen_opacities(entry)
                att = ft_layout.screen_attention(entry)
                dz = ft_layout.screen_follow_deadzone(entry)
                out.append({"index": i, "width": w, "height": h, "metres": ft_layout.screen_metres(layout, i),
                            "scale": round(s, 4), "primary": i == primary,
                            "curved": float(entry.get("curve", 0)) > 0,
                            "opacity": round(active, 3),
                            "activeOpacity": round(active, 3),
                            "idleOpacity": round(idle, 3),
                            "attentionEnabled": att["enabled"],
                            "attentionInMs": att["in_ms"],
                            "attentionOutMs": att["out_ms"],
                            "anchor": ft_layout.pin_anchor(entry.get("pin")) or "world",
                            "followDeadzone": dz["enabled"],
                            "followDeadzoneDeg": dz["degrees"],
                            "effective": f"{round(w / s)} × {round(h / s)}"})
            return out
        for i in range(c["screens"]):
            s = ft_layout.screen_scale(layout, i)
            rot = ft_layout.screen_rotation(layout, i)
            w, h = (c["height"], c["width"]) if rot != "normal" else (c["width"], c["height"])
            out.append({"index": i, "scale": round(s, 4), "rotation": rot,
                        "effective": f"{round(w / s)} × {round(h / s)}"})
        return out

    @Property("QVariantMap", notify=changed)
    def layout(self):
        return ft_layout.load_layout()

    @Property("QVariantMap", notify=changed)
    def profiles(self):
        store = ft_layout.load_profiles()
        slots = ft_layout.normalized_slots(store)
        current_slot = 0
        for i, name in enumerate(slots, 1):
            if name and name == store.get("current"):
                current_slot = i
                break
        return {
            "current": store["current"],
            "names": sorted(store["profiles"]),
            "slots": [{"index": i, "profile": n or ""} for i, n in enumerate(slots, 1)],
            "current_slot": current_slot,
        }

    def _instrument_card(self, iid):
        layout = ft_layout.load_layout()
        inst = ft_layout.instrument_entry(layout, iid) or ft_layout.default_instrument(iid)
        att = inst.get("attention") or {}
        default_m = (ft_layout.DEFAULT_BATTERY_METRES if iid == "battery"
                     else ft_layout.DEFAULT_STORAGE_METRES if iid in ("storage", "sd")
                     else ft_layout.DEFAULT_DATE_METRES if iid == "date"
                     else ft_layout.DEFAULT_MEDIA_METRES if iid == "media"
                     else ft_layout.DEFAULT_INSTRUMENT_METRES)
        return {
            "enabled": bool(inst.get("enabled")),
            "anchor": ft_layout.pin_anchor(inst.get("pin")) or "world",
            "metres": float(inst.get("metres", default_m)),
            "activeOpacity": float(inst.get("active_opacity", 1.0)),
            "idleOpacity": float(inst.get("idle_opacity", ft_layout.DEFAULT_INSTRUMENT_IDLE)),
            "attentionEnabled": bool(att.get("enabled", True)),
            "color": ft_layout.normalize_instrument_color(inst.get("color")),
        }

    @Property("QVariantMap", notify=changed)
    def clockInstrument(self):
        """Spatial Instruments — Clock card."""
        return self._instrument_card("clock")

    @Property("QVariantMap", notify=changed)
    def dateInstrument(self):
        """Spatial Instruments — Date card (weekday + day + month)."""
        return self._instrument_card("date")

    @Property("QVariantMap", notify=changed)
    def batteryInstrument(self):
        """Spatial Instruments — Battery card (Steam Frame headset)."""
        return self._instrument_card("battery")

    @Property("QVariantMap", notify=changed)
    def storageInstrument(self):
        """Spatial Instruments — internal device storage (summed mounts)."""
        return self._instrument_card("storage")

    @Property("QVariantMap", notify=changed)
    def sdInstrument(self):
        """Spatial Instruments — SD / mmc card storage."""
        return self._instrument_card("sd")

    @Property("QVariantMap", notify=changed)
    def mediaInstrument(self):
        """Spatial Instruments — Media (MPRIS now-playing + transport)."""
        return self._instrument_card("media")

    @Property("QVariantList", notify=changed)
    def plan(self):
        """The arrangement in the head frame, for the preview."""
        layout = ft_layout.load_layout()
        c = self._conf()
        # Before any panel was measured: the width SteamVR floats a panel at, and the aspect.
        if "panel_size" not in layout or layout["panel_size"] == list(ft_layout.DEFAULT_PANEL):
            layout["panel_size"] = [ft_layout.DEFAULT_PANEL[0], ft_layout.DEFAULT_PANEL[0] * c["height"] / c["width"]]
        out = []
        for i, t in enumerate(ft_layout.plan(layout, c["screens"])):
            w, h = ft_layout.screen_size(layout, i)
            out.append({"index": i, "x": t["pos"][0], "y": t["pos"][1], "z": t["pos"][2],
                        "faceYaw": t["face"][0], "facePitch": t["face"][1], "width": w, "height": h})
        return out

    @Property(str, notify=busyChanged)
    def busy(self):
        return self._busy

    # --- screens ---
    @Slot(int)
    def setScreens(self, n):
        write_conf_value("SCREENS", str(max(1, min(6, n))))
        self.changed.emit()

    @Slot(int, int)
    def setResolution(self, w, h):
        if w * h > MAX_PIXELS:
            self.message.emit(f"{w} × {h} is more than gamescope's VR mode can draw (1920 × 1080 worth of pixels, "
                              f"about {MAX_PIXELS // 1000} thousand); try {round((MAX_PIXELS * w / h) ** 0.5) // 8 * 8} × "
                              f"{round((MAX_PIXELS * h / w) ** 0.5) // 8 * 8}", True)
            return
        if w >= 640 and h >= 360:
            write_conf_value("WIDTH", str(w))
            write_conf_value("HEIGHT", str(h))
            self.changed.emit()

    @Slot(float)
    def setPhysWidth(self, w):
        write_conf_value("PHYS_WIDTH", f"{w:.2f}")
        self.changed.emit()

    @Slot(int, float)
    def setScale(self, i, s):
        layout = ft_layout.load_layout()
        screens = layout.setdefault("screens", [])
        while len(screens) <= i:
            screens.append({})
        screens[i]["scale"] = s
        ft_layout.save_layout(layout)
        self.changed.emit()
        if self._running:
            self._run("Applying scale", "scale")

    @Slot(int, str)
    def setRotation(self, i, rotation):
        layout = ft_layout.load_layout()
        screens = layout.setdefault("screens", [])
        while len(screens) <= i:
            screens.append({})
        screens[i]["rotation"] = rotation
        screens[i].pop("roll", None)  # a saved arrangement follows the new rotation
        ft_layout.save_layout(layout)
        self.changed.emit()
        if self._running:
            self._run("Rotating", "scale")

    # --- ft-screens: per-screen resolution and size ---
    def _edit_screen(self, i, fn):
        layout = ft_layout.load_layout()
        screens = layout.setdefault("screens", [])
        while len(screens) <= i:
            screens.append({"size": [1920, 1080], "metres": 1920 / ft_layout.PIXELS_PER_METRE})
        fn(screens[i])
        ft_layout.save_layout(layout)
        self.changed.emit()

    @Slot(int, int, int)
    def setScreenSize(self, i, w, h):
        if not (320 <= w <= 16384 and 200 <= h <= 16384):
            self.message.emit("Width and height: 320 to 16384 pixels", True)
            return
        self._edit_screen(i, lambda s: s.__setitem__("size", [w, h]))
        if self._running and i < self._running_count:
            self._ask_screens(f"size {i + 1} {w} {h}")

    @Slot(int, float)
    def setScreenMetres(self, i, m):
        self._edit_screen(i, lambda s: s.__setitem__("metres", round(m, 3)))
        if self._running and i < self._running_count:
            self._ask_screens(f"width {i + 1} {m:.3f}")

    @Slot(int, float)
    def setScreenOpacity(self, i, opacity):
        """Legacy single-opacity setter: sets active=idle=opacity, leaves attention alone."""
        opacity = max(0.0, min(1.0, float(opacity)))
        def edit(s):
            s["opacity"] = round(opacity, 3)
            s["active_opacity"] = round(opacity, 3)
            s["idle_opacity"] = round(opacity, 3)
        self._edit_screen(i, edit)
        if self._running and i < self._running_count:
            self._ask_screens(f"opacity {i + 1} {opacity:.3f} {opacity:.3f}")

    @Slot(int, float, float)
    def setScreenOpacities(self, i, active, idle):
        active = max(0.0, min(1.0, float(active)))
        idle = max(0.0, min(1.0, float(idle)))
        def edit(s):
            s["opacity"] = round(active, 3)
            s["active_opacity"] = round(active, 3)
            s["idle_opacity"] = round(idle, 3)
        self._edit_screen(i, edit)
        if self._running and i < self._running_count:
            self._ask_screens(f"opacity {i + 1} {active:.3f} {idle:.3f}")

    @Slot(int, bool)
    def setScreenAttention(self, i, enabled):
        def edit(s):
            att = ft_layout.screen_attention(s)
            att["enabled"] = bool(enabled)
            if enabled:
                s["attention"] = att
            else:
                s.pop("attention", None)
        self._edit_screen(i, edit)
        if self._running and i < self._running_count:
            if enabled:
                att = ft_layout.screen_attention(ft_layout.screen_entry(ft_layout.load_layout(), i))
                self._ask_screens(f"attention {i + 1} on {att['in_ms']:.0f} {att['out_ms']:.0f} "
                                  f"{att['dwell_ms']:.0f} {att['hold_ms']:.0f}")
            else:
                self._ask_screens(f"attention {i + 1} off")

    def _set_attention_ms(self, i, key, ms):
        ms = max(50.0, min(1000.0, float(ms)))
        def edit(s):
            att = ft_layout.screen_attention(s)
            att["enabled"] = True
            att[key] = ms
            s["attention"] = att
        self._edit_screen(i, edit)
        if self._running and i < self._running_count:
            att = ft_layout.screen_attention(ft_layout.screen_entry(ft_layout.load_layout(), i))
            self._ask_screens(f"attention {i + 1} on {att['in_ms']:.0f} {att['out_ms']:.0f} "
                              f"{att['dwell_ms']:.0f} {att['hold_ms']:.0f}")

    @Slot(int, float)
    def setScreenAttentionInMs(self, i, ms):
        """Fade toward active opacity when gazed (milliseconds)."""
        self._set_attention_ms(i, "in_ms", ms)

    @Slot(int, float)
    def setScreenAttentionOutMs(self, i, ms):
        """Fade toward idle opacity when gaze leaves (milliseconds)."""
        self._set_attention_ms(i, "out_ms", ms)

    def _push_follow_deadzone(self, i):
        dz = ft_layout.screen_follow_deadzone(ft_layout.screen_entry(ft_layout.load_layout(), i))
        if self._running and i < self._running_count:
            if dz["enabled"]:
                self._ask_screens(f"deadzone {i + 1} on {dz['degrees']:.1f} {dz['metres']:.3f}")
            else:
                self._ask_screens(f"deadzone {i + 1} off")

    @Slot(int, bool)
    def setScreenFollowDeadzone(self, i, enabled):
        """Soft-follow glance dead zone: small head turns don't chase the panel."""
        def edit(s):
            dz = ft_layout.screen_follow_deadzone(s)
            dz["enabled"] = bool(enabled)
            if enabled:
                s["follow_deadzone"] = dz
            else:
                s.pop("follow_deadzone", None)
        self._edit_screen(i, edit)
        self._push_follow_deadzone(i)

    @Slot(int, float)
    def setScreenFollowDeadzoneDeg(self, i, degrees):
        def edit(s):
            dz = ft_layout.screen_follow_deadzone(s)
            dz["enabled"] = True
            dz["degrees"] = max(1.0, min(90.0, float(degrees)))
            s["follow_deadzone"] = dz
        self._edit_screen(i, edit)
        self._push_follow_deadzone(i)

    @Slot(int, str)
    def setScreenAnchor(self, i, mode):
        mode = ft_layout.normalize_anchor(mode) or "world"
        def edit(s):
            if mode == "world":
                s.pop("pin", None)
            # Live pin needs a current relative transform from ft-screens; ask it.
        self._edit_screen(i, edit)
        if self._running and i < self._running_count:
            self._ask_screens(f"pin {i + 1} {mode}")
            # Re-capture so layout pin matches live seed (no pop on next apply).
            try:
                ft_layout.capture_screens()
            except RuntimeError:
                pass
            self.changed.emit()

    @Slot(int, bool)
    def setCurved(self, i, on):
        """Curve a screen into a cylinder around you (radius: your distance to it now, from
        ft-screens; the layout's distance if the desktop isn't running)."""
        radius = float(ft_layout.load_layout()["preset"].get("distance", 2.0)) if on else 0.0
        if self._running and i < self._running_count:
            reply = self._ask_screens(f"curve {i + 1} {'on' if on else 'off'}")
            if reply and reply.startswith("ok"):
                radius = float(reply.split()[1])
        self._edit_screen(i, lambda s: s.__setitem__("curve", round(radius, 3)))

    @Slot(int)
    def setPrimary(self, i):
        layout = ft_layout.load_layout()
        layout["primary"] = i + 1
        ft_layout.save_layout(layout)
        self.changed.emit()
        if self._running:
            self._run("Moving the taskbar", "scale")

    @Slot()
    def addScreen(self):
        layout = ft_layout.load_layout()
        layout.setdefault("screens", []).append({"size": [1920, 1080], "metres": 1920 / ft_layout.PIXELS_PER_METRE})
        ft_layout.save_layout(layout)
        self.changed.emit()

    @Slot(int)
    def removeScreen(self, i):
        layout = ft_layout.load_layout()
        screens = layout.get("screens", [])
        if len(screens) <= 1 or i >= len(screens):
            return
        screens.pop(i)
        if layout.get("primary") == i + 1:
            layout.pop("primary")
        ft_layout.save_layout(layout)
        self.changed.emit()

    @Slot()
    def toggleScreens(self):
        self._ask_screens("toggle")

    # --- ft-screens: visibility and pinning ---
    @Property("QVariantMap", notify=changed)
    def visibility(self):
        return ft_layout.visibility(ft_layout.load_layout())

    @Slot(str, "QVariant")
    def setVisibility(self, key, value):
        layout = ft_layout.load_layout()
        v = ft_layout.visibility(layout)
        v[key] = value
        layout["visibility"] = v
        ft_layout.save_layout(layout)
        self.changed.emit()
        if self._running:
            if key == "mode":
                self._ask_screens(f"visibility {value}")
            elif key == "wrist_angle":
                self._ask_screens(f"wrist {float(value):.1f}")
            elif key == "controllers":
                self._ask_screens(f"controllers {value}")
            elif key == "in_games":
                self._ask_screens(f"ingames {value}")
            else:
                self._ask_screens(f"gesture {v['gesture_hand']} {float(v['gesture_angle']):.1f}")

    @Slot(str)
    def pinAll(self, hand):
        reply = self._ask_screens(f"pin all {hand}") if self._running else None
        if reply and reply.startswith("ok"):
            labels = {
                "head": "your headset (soft follow)",
                "head-rigid": "your headset (rigid)",
                "yaw-follow": "yaw-follow (upright while turning)",
                "position-follow": "position-follow (translation only)",
                "left": "your left wrist",
                "right": "your right wrist",
            }
            where = labels.get(hand, hand)
            self.message.emit(f"All screens ride on {where} now; grab a screen's bar to take it off. "
                              "Save current arrangement / Save profile keeps it.", False)
        else:
            self.message.emit(f"Couldn't pin: {reply or 'the desktop is not running'}", True)

    @Slot()
    def unpinAll(self):
        reply = self._ask_screens("unpin all") if self._running else None
        if not (reply and reply.startswith("ok")):
            self.message.emit(f"Couldn't unpin: {reply or 'the desktop is not running'}", True)

    def _edit_instrument(self, iid, mutate):
        layout = ft_layout.load_layout()
        inst = ft_layout.instrument_entry(layout, iid) or ft_layout.default_instrument(iid)
        mutate(inst)
        layout = ft_layout.upsert_instrument(layout, inst)
        ft_layout.save_layout(layout)
        self.changed.emit()
        return inst

    def _edit_clock(self, mutate):
        return self._edit_instrument("clock", mutate)

    def _edit_date(self, mutate):
        return self._edit_instrument("date", mutate)

    def _edit_battery(self, mutate):
        return self._edit_instrument("battery", mutate)

    def _edit_storage(self, mutate):
        return self._edit_instrument("storage", mutate)

    def _edit_sd(self, mutate):
        return self._edit_instrument("sd", mutate)

    def _set_instrument_enabled(self, iid, label, enabled):
        self._edit_instrument(iid, lambda i: i.__setitem__("enabled", bool(enabled)))
        if self._running:
            self._run(label, "instrument", "enable" if enabled else "disable", iid)

    def _set_instrument_anchor(self, iid, mode):
        mode = ft_layout.normalize_anchor(mode) or "world"
        if mode not in ft_layout.INSTRUMENT_ANCHORS:
            mode = "world"

        def edit(inst):
            if mode == "world":
                inst.pop("pin", None)
            else:
                rel = (inst.get("pin") or {}).get("rel") or [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0]
                inst["pin"] = ft_layout.make_pin(mode, rel)

        self._edit_instrument(iid, edit)
        if self._running:
            if mode == "world":
                self._ask_screens(f"instrument unpin {iid}")
            else:
                self._ask_screens(f"instrument pin {iid} {mode}")

    def _set_instrument_metres(self, iid, metres):
        metres = max(0.08, min(2.0, float(metres)))
        self._edit_instrument(iid, lambda i: i.__setitem__("metres", metres))
        if self._running:
            self._ask_screens(f"instrument width {iid} {metres:.4f}")

    def _set_instrument_active_opacity(self, iid, value):
        value = max(0.0, min(1.0, float(value)))

        def edit(inst):
            inst["active_opacity"] = value
            inst["opacity"] = value

        inst = self._edit_instrument(iid, edit)
        if self._running:
            self._ask_screens(
                f"instrument opacity {iid} {inst['active_opacity']:.3f} {inst['idle_opacity']:.3f}")

    def _set_instrument_idle_opacity(self, iid, value):
        value = max(0.0, min(1.0, float(value)))

        def edit(inst):
            inst["idle_opacity"] = value

        inst = self._edit_instrument(iid, edit)
        if self._running:
            self._ask_screens(
                f"instrument opacity {iid} {inst['active_opacity']:.3f} {inst['idle_opacity']:.3f}")

    def _set_instrument_attention(self, iid, enabled):
        def edit(inst):
            att = dict(inst.get("attention") or ft_layout.screen_attention({}))
            att["enabled"] = bool(enabled)
            inst["attention"] = att

        self._edit_instrument(iid, edit)
        if self._running:
            self._ask_screens(f"instrument attention {iid} {'on' if enabled else 'off'}")

    def _set_instrument_color(self, iid, color):
        color = ft_layout.normalize_instrument_color(color)
        self._edit_instrument(iid, lambda i: i.__setitem__("color", color))
        if self._running:
            self._ask_screens(f"instrument color {iid} {color}")

    def _recenter_instrument(self, iid, label):
        self._edit_instrument(iid, lambda i: i.__setitem__("enabled", True))
        if self._running:
            self._run(label, "instrument", "recenter", iid)
        else:
            self.message.emit(f"Desktop not running — enable {label} when Frametop is up", False)

    @Slot(bool)
    def setClockEnabled(self, enabled):
        self._set_instrument_enabled("clock", "Clock", enabled)

    @Slot(str)
    def setClockAnchor(self, mode):
        self._set_instrument_anchor("clock", mode)

    @Slot(float)
    def setClockMetres(self, metres):
        self._set_instrument_metres("clock", metres)

    @Slot(float)
    def setClockActiveOpacity(self, value):
        self._set_instrument_active_opacity("clock", value)

    @Slot(float)
    def setClockIdleOpacity(self, value):
        self._set_instrument_idle_opacity("clock", value)

    @Slot(bool)
    def setClockAttention(self, enabled):
        self._set_instrument_attention("clock", enabled)

    @Slot(str)
    def setClockColor(self, color):
        self._set_instrument_color("clock", color)

    @Slot()
    def recenterClock(self):
        self._recenter_instrument("clock", "Clock")

    @Slot(bool)
    def setDateEnabled(self, enabled):
        self._set_instrument_enabled("date", "Date", enabled)

    @Slot(str)
    def setDateAnchor(self, mode):
        self._set_instrument_anchor("date", mode)

    @Slot(float)
    def setDateMetres(self, metres):
        self._set_instrument_metres("date", metres)

    @Slot(float)
    def setDateActiveOpacity(self, value):
        self._set_instrument_active_opacity("date", value)

    @Slot(float)
    def setDateIdleOpacity(self, value):
        self._set_instrument_idle_opacity("date", value)

    @Slot(bool)
    def setDateAttention(self, enabled):
        self._set_instrument_attention("date", enabled)

    @Slot(str)
    def setDateColor(self, color):
        self._set_instrument_color("date", color)

    @Slot()
    def recenterDate(self):
        self._recenter_instrument("date", "Date")

    @Slot(bool)
    def setBatteryEnabled(self, enabled):
        self._set_instrument_enabled("battery", "Battery", enabled)

    @Slot(str)
    def setBatteryAnchor(self, mode):
        self._set_instrument_anchor("battery", mode)

    @Slot(float)
    def setBatteryMetres(self, metres):
        self._set_instrument_metres("battery", metres)

    @Slot(float)
    def setBatteryActiveOpacity(self, value):
        self._set_instrument_active_opacity("battery", value)

    @Slot(float)
    def setBatteryIdleOpacity(self, value):
        self._set_instrument_idle_opacity("battery", value)

    @Slot(bool)
    def setBatteryAttention(self, enabled):
        self._set_instrument_attention("battery", enabled)

    @Slot(str)
    def setBatteryColor(self, color):
        self._set_instrument_color("battery", color)

    @Slot()
    def recenterBattery(self):
        self._recenter_instrument("battery", "Battery")

    @Slot(bool)
    def setStorageEnabled(self, enabled):
        self._set_instrument_enabled("storage", "Storage", enabled)

    @Slot(str)
    def setStorageAnchor(self, mode):
        self._set_instrument_anchor("storage", mode)

    @Slot(float)
    def setStorageMetres(self, metres):
        self._set_instrument_metres("storage", metres)

    @Slot(float)
    def setStorageActiveOpacity(self, value):
        self._set_instrument_active_opacity("storage", value)

    @Slot(float)
    def setStorageIdleOpacity(self, value):
        self._set_instrument_idle_opacity("storage", value)

    @Slot(bool)
    def setStorageAttention(self, enabled):
        self._set_instrument_attention("storage", enabled)

    @Slot()
    def recenterStorage(self):
        self._recenter_instrument("storage", "Storage")

    @Slot(bool)
    def setSdEnabled(self, enabled):
        self._set_instrument_enabled("sd", "SD card", enabled)

    @Slot(str)
    def setSdAnchor(self, mode):
        self._set_instrument_anchor("sd", mode)

    @Slot(float)
    def setSdMetres(self, metres):
        self._set_instrument_metres("sd", metres)

    @Slot(float)
    def setSdActiveOpacity(self, value):
        self._set_instrument_active_opacity("sd", value)

    @Slot(float)
    def setSdIdleOpacity(self, value):
        self._set_instrument_idle_opacity("sd", value)

    @Slot(bool)
    def setSdAttention(self, enabled):
        self._set_instrument_attention("sd", enabled)

    @Slot()
    def recenterSd(self):
        self._recenter_instrument("sd", "SD card")

    @Slot(bool)
    def setMediaEnabled(self, enabled):
        self._set_instrument_enabled("media", "Media", enabled)

    @Slot(str)
    def setMediaAnchor(self, mode):
        self._set_instrument_anchor("media", mode)

    @Slot(float)
    def setMediaMetres(self, metres):
        self._set_instrument_metres("media", metres)

    @Slot(float)
    def setMediaActiveOpacity(self, value):
        self._set_instrument_active_opacity("media", value)

    @Slot(float)
    def setMediaIdleOpacity(self, value):
        self._set_instrument_idle_opacity("media", value)

    @Slot(bool)
    def setMediaAttention(self, enabled):
        self._set_instrument_attention("media", enabled)

    @Slot()
    def recenterMedia(self):
        self._recenter_instrument("media", "Media")

    @Slot(str)
    def applyProfile(self, name):
        if not name:
            self.message.emit("Pick a profile first", True)
            return
        self._run("Applying profile", "profile", "apply", name)

    @Slot(str)
    def saveProfile(self, name):
        name = (name or "").strip()
        if not name:
            self.message.emit("Enter a profile name", True)
            return
        self._run("Saving profile", "profile", "save", name)

    @Slot(str)
    def deleteProfile(self, name):
        if not name:
            self.message.emit("Pick a profile first", True)
            return
        self._run("Deleting profile", "profile", "delete", name)

    @Slot(int, str)
    def assignProfileSlot(self, slot, name):
        slot = int(slot)
        name = (name or "").strip()
        if not 1 <= slot <= ft_layout.SLOT_COUNT:
            self.message.emit(f"Slot must be 1..{ft_layout.SLOT_COUNT}", True)
            return
        if not name:
            self._run("Clearing slot", "profile", "unslot", str(slot))
            return
        self._run("Assigning slot", "profile", "slot", str(slot), name)

    @Slot(int)
    def clearProfileSlot(self, slot):
        self.assignProfileSlot(slot, "")

    @Slot(int)
    def applyProfileSlot(self, slot):
        self._run("Applying slot", "action", f"profile.slot.{int(slot)}")

    @Slot()
    def restartDesktop(self):
        """Restart the Frametop desktop (this app closes with it) to apply count and resolution."""
        argv = host_command("systemd-run", "--user", "--collect", "--quiet", os.path.abspath(DESKTOPS), "restart")
        QProcess.startDetached(argv[0], argv[1:])
        self.message.emit("Restarting the desktop…", False)

    # --- layout ---
    def _edit_layout(self, fn):
        layout = ft_layout.load_layout()
        fn(layout)
        ft_layout.save_layout(layout)
        self.changed.emit()

    @Slot(str)
    def setMode(self, mode):
        self._edit_layout(lambda l: l.__setitem__("mode", mode))

    @Slot(str, "QVariant")
    def setPreset(self, key, value):
        def edit(layout):
            layout["mode"] = "preset"
            layout["preset"][key] = value
        self._edit_layout(edit)

    @Slot(bool)
    def setAuto(self, on):
        self._edit_layout(lambda l: l.__setitem__("auto", bool(on)))

    @Slot()
    def arrange(self):
        self._run("Arranging the screens", "apply")

    @Slot()
    def capture(self):
        self._run("Saving the current arrangement", "capture")

    # --- ft-layout on the host ---
    def _run(self, label, *args):
        if self._proc is not None:
            self.message.emit(f"Still busy: {self._busy}", True)
            return
        self._busy = label
        self.busyChanged.emit()
        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        argv = host_command(os.path.abspath(FT_LAYOUT), *args)
        proc.finished.connect(lambda code, _status: self._done(proc, label, code))
        self._proc = proc
        proc.start(argv[0], argv[1:])

    def _done(self, proc, label, code):
        out = bytes(proc.readAllStandardOutput()).decode(errors="replace").strip()
        self._proc = None
        self._busy = ""
        self.busyChanged.emit()
        self.changed.emit()
        last = out.splitlines()[-1] if out else ""
        if code == 0:
            self.message.emit(f"{label}: done" + (f" ({last})" if last and not last.startswith("ok") else ""), False)
        else:
            self.message.emit(f"{label} failed: {last or 'exit code ' + str(code)}", True)


def main():
    app = QGuiApplication(sys.argv)
    app.setApplicationName("ft-display-settings")
    app.setApplicationDisplayName("Frametop Display Settings")
    app.setDesktopFileName("ft-display-settings")
    if not QIcon.themeName():
        QIcon.setThemeName("breeze")
    QQuickStyle.setStyle("org.kde.desktop")
    engine = QQmlApplicationEngine()
    backend = Backend()
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("startPage", os.environ.get("FT_DISPLAY_PAGE", "screens"))
    engine.load(QUrl.fromLocalFile(os.path.join(HERE, "main.qml")))
    if not engine.rootObjects():
        sys.exit(1)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
