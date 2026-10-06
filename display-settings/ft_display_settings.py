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
    dashboard open, hide whenever the dashboard opens, while you look at a controller,
    or only when toggled), the wrist angle within which a pinned screen shows, and pin
    or unpin all screens.
  - Spatial Instruments (ft-screens): grid of ambient overlays (Clock, Date, Battery,
    storage, Media, Image, Launcher) with example previews; Configure opens a sheet.
  - Layout: a preset (curved or flat, rows, distance, gap, height) or the arrangement
    captured from where the screens are now, with a preview; arrange now; save the
    current arrangement; arrange automatically when the desktop starts.
  - Background: SteamVR compositor skybox (Aurora / stock equirect / custom 360° image)
    via scripts/frame-background on the host.
Tab order: Screens → Layout → Visibility → Background → Spatial Instruments.
Settings go to ~/.config/frametop.conf and ~/.config/frametop-layout.json. Anything
that touches SteamVR runs layout/ft-layout (or frame-background) on the host.
Launch with display-settings/ft-display-settings (host wrapper).
"""
import os
import json
import shutil
import socket
import subprocess
import sys

from PySide6.QtCore import Property, QObject, QProcess, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication, QFileDialog

HERE = os.path.dirname(os.path.abspath(__file__))
LAYOUT_DIR = os.path.join(HERE, "..", "layout")
sys.path.insert(0, LAYOUT_DIR)
import ft_layout  # noqa: E402  (pure Python: the same geometry ft-layout uses)

FT_LAYOUT = os.path.join(LAYOUT_DIR, "ft-layout")
FRAME_BACKGROUND = os.path.join(HERE, "..", "scripts", "frame-background")
BACKGROUND_DIR = os.path.join(
    os.path.expanduser("~"), ".config", "openvr", "config", "frametop-backgrounds"
)
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
BACKGROUND_PRESETS = [
    {"id": "aurora", "text": "Aurora (procedural)"},
    {"id": "night_mountains", "text": "Night Mountains"},
    {"id": "aurorasky", "text": "Aurora Sky (still image)"},
]


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


def resolve_image_source_path(url_or_path):
    """Turn a FileDialog url/path into a local filesystem path.

    Display Settings runs in distrobox; the picker may return file:// URLs, percent-encoded
    paths, or portal document paths. Prefer a real path the host can open.
    """
    from PySide6.QtCore import QFile, QIODevice

    if isinstance(url_or_path, QUrl):
        url = QUrl(url_or_path)
    else:
        raw = str(url_or_path or "").strip()
        if not raw:
            return ""
        # QML selectedFile.toString() is usually file:///…; plain paths also appear.
        if raw.startswith("file:") or "://" in raw:
            url = QUrl(raw)
        else:
            url = QUrl.fromLocalFile(os.path.expanduser(raw))

    local = url.toLocalFile() if url.isValid() else ""
    if local:
        local = os.path.expanduser(local)
        if os.path.isfile(local):
            return os.path.abspath(local)

    # Portal / FUSE doc paths: QFile can often read them when os.path.isfile cannot
    # (or the path only resolves briefly). Materialize into /tmp for the host copy.
    qf = QFile(url.toString() if url.isValid() else (local or ""))
    if qf.open(QIODevice.ReadOnly):
        data = bytes(qf.readAll())
        qf.close()
        if data:
            name = url.fileName() if url.isValid() else ""
            ext = os.path.splitext(name or local or "")[1].lower()
            if ext not in (".png", ".gif", ".jpg", ".jpeg", ".bmp", ".webp", ".hdr", ".exr", ".hdri"):
                # Sniff a few magic bytes when the dialog strips the extension.
                if data[:6] in (b"GIF87a", b"GIF89a"):
                    ext = ".gif"
                elif data[:8] == b"\x89PNG\r\n\x1a\n":
                    ext = ".png"
                elif data[:2] == b"\xff\xd8":
                    ext = ".jpg"
                elif data[:10].startswith(b"#?RADIANCE") or data[:6] == b"#?RGBE":
                    ext = ".hdr"
                else:
                    ext = ".png"
            tmp_dir = os.path.join(os.path.expanduser("~"), ".cache", "frametop")
            os.makedirs(tmp_dir, exist_ok=True)
            tmp = os.path.join(tmp_dir, f"image-pick-{os.getpid()}{ext}")
            with open(tmp, "wb") as f:
                f.write(data)
            return tmp

    # Last resort: return the absolute path so host-side ft-layout can try
    # (e.g. /run/media/... visible on the host but not in the container).
    if local:
        return os.path.abspath(local) if os.path.isabs(local) else local
    return ""


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
        # Abstract UNIX datagram to ft-screens. Missing on Windows (PC edit/test) —
        # Backend still works for QML API / background helpers that shell out.
        self._sock = None
        if hasattr(socket, "AF_UNIX"):
            try:
                self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
                self._sock.bind("")  # an abstract address ft-screens can reply to
                self._sock.settimeout(1.0)
            except OSError:
                self._sock = None
        self._started = {}  # conf values the running desktop started with
        self._bg = {
            "mode": "",
            "preset": "",
            "background": "",
            "exists": False,
            "width": 0,
            "height": 0,
            "error": "",
        }
        self.poll = QTimer(interval=3000, timeout=self._check_running)
        if hasattr(os, "getuid"):
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
        if not hasattr(os, "getuid"):
            return
        running = os.path.exists(f"/run/user/{os.getuid()}/frametop/wayland-0")
        count = self._screens_running() if running and ft_layout.backend() == "screens" else 0
        if running != self._running or count != self._running_count:
            self._running = running
            self._running_count = count
            self._started = self._conf() if running else {}
            self.changed.emit()

    def _ask_screens(self, text):
        """Request/reply to ft-screens; None if it isn't running."""
        if self._sock is None:
            return None
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
        itype = ft_layout.instrument_type_for_id(iid) or iid
        inst = ft_layout.instrument_entry(layout, iid) or (
            ft_layout.default_image_instrument(iid) if itype == "image"
            else ft_layout.default_launcher_instrument(iid) if itype == "launcher"
            else ft_layout.default_instrument(itype))
        att = inst.get("attention") or {}
        default_m = (ft_layout.DEFAULT_BATTERY_METRES if itype == "battery"
                     else ft_layout.DEFAULT_STORAGE_METRES if itype in ("storage", "sd")
                     else ft_layout.DEFAULT_DATE_METRES if itype == "date"
                     else ft_layout.DEFAULT_MEDIA_METRES if itype == "media"
                     else ft_layout.DEFAULT_IMAGE_METRES if itype == "image"
                     else ft_layout.DEFAULT_LAUNCHER_METRES if itype == "launcher"
                     else ft_layout.DEFAULT_INSTRUMENT_METRES)
        card = {
            "id": iid,
            "type": itype,
            "enabled": bool(inst.get("enabled")),
            "anchor": ft_layout.pin_anchor(inst.get("pin")) or "world",
            "metres": float(inst.get("metres", default_m)),
            "activeOpacity": float(inst.get("active_opacity", 1.0)),
            "idleOpacity": float(inst.get("idle_opacity",
                                          ft_layout.DEFAULT_LAUNCHER_IDLE if itype == "launcher"
                                          else ft_layout.DEFAULT_INSTRUMENT_IDLE)),
            "attentionEnabled": bool(att.get("enabled", True)),
            "color": ft_layout.normalize_instrument_color(inst.get("color")),
        }
        if itype == "image":
            path = str(inst.get("path") or "")
            card["path"] = path
            card["fileName"] = os.path.basename(path) if path else ""
            card["label"] = "Image" if iid == "image" else f"Image ({iid})"
        if itype == "launcher":
            path = str(inst.get("path") or "")
            card["path"] = path
            card["fileName"] = os.path.basename(path) if path else ""
            card["actionKind"] = inst.get("action_kind") or "application"
            card["desktopId"] = inst.get("desktop_id") or ""
            card["semantic"] = inst.get("semantic") or ""
            card["commandShell"] = bool(inst.get("command_shell"))
            cmd = inst.get("command") or []
            card["commandText"] = (" ".join(cmd) if isinstance(cmd, list) else str(cmd or ""))
            card["appearance"] = inst.get("appearance") or "app"
            card["glyph"] = inst.get("glyph") or "star"
            name = inst.get("label") or ""
            if not name and card["desktopId"]:
                name = card["desktopId"].replace(".desktop", "")
            card["label"] = name or (iid if iid != "launcher" else "Launcher")
            card["title"] = "Launcher" if iid == "launcher" else f"Launcher ({iid})"
            # Stale app hint for Display Settings (host + container .desktop dirs).
            available = True
            if card["actionKind"] == "application" and card["desktopId"]:
                try:
                    import ft_desktop
                    available = ft_desktop.application_available(card["desktopId"])
                except Exception:
                    available = True
            card["appAvailable"] = available
            # Also expose whether the id is in the chooser list (UI can recompute live).
            card["appInChooser"] = available
        return card

    @Property("QVariantList", notify=changed)
    def instrumentColorPresets(self):
        """Cyberpunk CRT / phosphor colour presets for coloured instruments."""
        return [{"text": name, "value": value} for name, value in ft_layout.INSTRUMENT_COLOR_PRESETS]

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
    def imageInstruments(self):
        """All Image Spatial Instruments (image, image-2, …). Empty list if none configured."""
        layout = ft_layout.load_layout()
        items = [i for i in ft_layout.instruments_from_layout(layout) if i.get("type") == "image"]
        if not items:
            # Show one empty card so the user can enable/upload without Add first.
            return [self._instrument_card("image")]
        return [self._instrument_card(i["id"]) for i in items]

    @Property("QVariantList", notify=changed)
    def launcherInstruments(self):
        """All Launcher Spatial Instruments (launcher, launcher-2, …)."""
        layout = ft_layout.load_layout()
        items = [i for i in ft_layout.instruments_from_layout(layout) if i.get("type") == "launcher"]
        return [self._instrument_card(i["id"]) for i in items]

    @Property("QVariantList", notify=changed)
    def installedApps(self):
        """Visible .desktop applications for the Launcher chooser."""
        try:
            import ft_desktop
            apps = ft_desktop.list_applications()
        except Exception:
            return []
        return [{"id": a["id"], "name": a["name"], "icon": a.get("icon") or ""} for a in apps]

    @Property("QVariantList", notify=changed)
    def semanticActions(self):
        """Frametop/Asterism semantic actions for Launcher action type."""
        return [{"id": a, "label": ft_layout.ACTION_LABELS.get(a, a)} for a in ft_layout.SEMANTIC_ACTIONS]

    @Property("QVariantList", notify=changed)
    def launcherGlyphs(self):
        try:
            import ft_desktop
            return list(ft_desktop.LAUNCHER_GLYPHS)
        except Exception:
            return ["star", "play", "terminal", "gear"]

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

    # --- SteamVR compositor background (host frame-background CLI) ---
    @Property("QVariantList", constant=True)
    def backgroundPresets(self):
        return list(BACKGROUND_PRESETS)

    @Property(str, notify=changed)
    def backgroundMode(self):
        return self._bg.get("mode") or ""

    @Property(str, notify=changed)
    def backgroundPreset(self):
        return self._bg.get("preset") or ""

    @Property(str, notify=changed)
    def backgroundPath(self):
        return self._bg.get("background") or ""

    @Property(str, notify=changed)
    def backgroundFileName(self):
        path = self._bg.get("background") or ""
        return os.path.basename(path) if path else ""

    @Property(bool, notify=changed)
    def backgroundExists(self):
        return bool(self._bg.get("exists"))

    @Property(str, notify=changed)
    def backgroundSizeText(self):
        w, h = int(self._bg.get("width") or 0), int(self._bg.get("height") or 0)
        if not w or not h:
            return ""
        ratio = w / h
        note = " (~2:1 equirect)" if abs(ratio - 2.0) < 0.15 else f" (ratio {ratio:.2f}; prefer ~2:1)"
        return f"{w} × {h}{note}"

    @Property(str, notify=changed)
    def backgroundError(self):
        return self._bg.get("error") or ""

    @Property(str, constant=True)
    def backgroundDirectory(self):
        return BACKGROUND_DIR

    @Property(str, constant=True)
    def backgroundDirectoryUrl(self):
        """file:// URL for FileDialog.currentFolder."""
        return QUrl.fromLocalFile(BACKGROUND_DIR).toString()

    def _frame_background_argv(self, *args):
        return host_command("python3", os.path.abspath(FRAME_BACKGROUND), *args)

    def _apply_background_status(self, data, error=""):
        self._bg = {
            "mode": str(data.get("mode") or ""),
            "preset": str(data.get("preset") or ""),
            "background": str(data.get("background") or ""),
            "exists": bool(data.get("exists")),
            "width": int(data.get("width") or 0),
            "height": int(data.get("height") or 0),
            "error": error or "",
        }
        self.changed.emit()

    @Slot()
    def refreshBackground(self):
        """Read live SteamVR background settings via scripts/frame-background on the host."""
        argv = self._frame_background_argv("status", "--json")
        try:
            proc = subprocess.run(
                argv, capture_output=True, text=True, timeout=20, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            self._apply_background_status({}, error=str(e))
            return
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if proc.returncode != 0:
            self._apply_background_status(
                {},
                error=err or out or f"exit code {proc.returncode}",
            )
            return
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            self._apply_background_status({}, error=out or "invalid JSON from frame-background")
            return
        if not isinstance(data, dict):
            self._apply_background_status({}, error="unexpected status payload")
            return
        self._apply_background_status(data)

    def _run_background(self, label, *args):
        if self._proc is not None:
            self.message.emit(f"Still busy: {self._busy}", True)
            return
        self._busy = label
        self.busyChanged.emit()
        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        argv = self._frame_background_argv(*args)
        proc.finished.connect(lambda code, _status: self._done_background(proc, label, code))
        self._proc = proc
        proc.start(argv[0], argv[1:])

    def _done_background(self, proc, label, code):
        out = bytes(proc.readAllStandardOutput()).decode(errors="replace").strip()
        self._proc = None
        self._busy = ""
        self.busyChanged.emit()
        last = out.splitlines()[-1] if out else ""
        if code == 0:
            self.message.emit(
                f"{label}: done" + (f" ({last})" if last and not last.startswith("ok") else ""),
                False,
            )
        else:
            self.message.emit(f"{label} failed: {last or 'exit code ' + str(code)}", True)
        self.refreshBackground()

    @Slot(str)
    def setBackgroundPreset(self, preset_id):
        """preset_id: aurora | night_mountains | aurorasky"""
        preset_id = (preset_id or "").strip().lower()
        if preset_id == "aurora":
            self._run_background("Background Aurora", "aurora")
            return
        if preset_id in ("night_mountains", "aurorasky"):
            self._run_background("Background image", "set", preset_id)
            return
        self.message.emit(f"Unknown background preset: {preset_id}", True)

    @Slot("QVariant")
    def setBackgroundFile(self, url_or_path):
        """Apply a custom equirectangular image as the SteamVR skybox."""
        path = resolve_image_source_path(url_or_path)
        if not path:
            self.message.emit("Could not read that file (empty path from the picker)", True)
            return
        self._run_background("Background image", "set", path)

    @Slot()
    def pickBackgroundFile(self):
        """File picker that starts in frametop-backgrounds/ (QML portal dialogs ignore that)."""
        self.ensureBackgroundDirectory()
        if not os.path.isdir(BACKGROUND_DIR):
            return
        path, _selected_filter = QFileDialog.getOpenFileName(
            None,
            "Choose 360° equirectangular background",
            BACKGROUND_DIR,
            "Images (*.png *.jpg *.jpeg *.webp *.hdr *.exr);;All files (*)",
        )
        if path:
            self.setBackgroundFile(path)

    @Slot()
    def ensureBackgroundDirectory(self):
        """Create ~/.config/openvr/config/frametop-backgrounds/ if missing."""
        try:
            os.makedirs(BACKGROUND_DIR, exist_ok=True)
        except OSError as e:
            self.message.emit(f"Could not create background folder: {e}", True)

    @Slot()
    def openBackgroundDirectory(self):
        """Open ~/.config/openvr/config/frametop-backgrounds/ in the file manager."""
        self.ensureBackgroundDirectory()
        if not os.path.isdir(BACKGROUND_DIR):
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(BACKGROUND_DIR)):
            self.message.emit(f"Could not open {BACKGROUND_DIR}", True)
            return
        self.message.emit(f"Opened {BACKGROUND_DIR}", False)

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
        if idle > active:
            active, idle = idle, active
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

    @Property("QVariantList", notify=changed)
    def screensShown(self):
        """For each screen, whether it shows (False: hidden on its own, ft-layout hide N)."""
        layout = ft_layout.load_layout()
        return [not ft_layout.screen_entry(layout, i).get("hidden") for i in range(ft_layout.screen_count(layout))]

    @Slot(int, bool)
    def setScreenShown(self, index, shown):
        """Hide screen `index` (0-based) on its own, whatever the visibility mode, or show it.
        Saved in the layout, and applied at once if the desktop runs."""
        try:
            ft_layout.set_hidden(str(index + 1), not shown)
        except RuntimeError as e:
            self.message.emit(f"Couldn't change the screen: {e}", True)
        self.changed.emit()

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
            idle = float(inst.get("idle_opacity", value))
            active = value
            if idle > active:
                active, idle = idle, active
            inst["active_opacity"] = active
            inst["idle_opacity"] = idle
            inst["opacity"] = active

        inst = self._edit_instrument(iid, edit)
        if self._running:
            self._ask_screens(
                f"instrument opacity {iid} {inst['active_opacity']:.3f} {inst['idle_opacity']:.3f}")

    def _set_instrument_idle_opacity(self, iid, value):
        value = max(0.0, min(1.0, float(value)))

        def edit(inst):
            active = float(inst.get("active_opacity", 1.0))
            idle = value
            if idle > active:
                active, idle = idle, active
            inst["active_opacity"] = active
            inst["idle_opacity"] = idle
            inst["opacity"] = active

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

    @Slot(str)
    def setMediaColor(self, color):
        self._set_instrument_color("media", color)

    @Slot()
    def recenterMedia(self):
        self._recenter_instrument("media", "Media")

    @Slot(str, bool)
    def setImageEnabled(self, iid, enabled):
        self._set_instrument_enabled(iid or "image", "Image", enabled)

    @Slot(str, str)
    def setImageAnchor(self, iid, mode):
        self._set_instrument_anchor(iid or "image", mode)

    @Slot(str, float)
    def setImageMetres(self, iid, metres):
        self._set_instrument_metres(iid or "image", metres)

    @Slot(str, float)
    def setImageActiveOpacity(self, iid, value):
        self._set_instrument_active_opacity(iid or "image", value)

    @Slot(str, float)
    def setImageIdleOpacity(self, iid, value):
        self._set_instrument_idle_opacity(iid or "image", value)

    @Slot(str, bool)
    def setImageAttention(self, iid, enabled):
        self._set_instrument_attention(iid or "image", enabled)

    @Slot(str)
    def recenterImage(self, iid):
        self._recenter_instrument(iid or "image", "Image")

    @Slot(str, "QVariant")
    def setImageFile(self, iid, url_or_path):
        """Copy a chosen image into ~/.config/frametop-instruments/{iid}.* and push to ft-screens.

        Installs via host ft-layout: the file dialog runs in distrobox, and many paths
        (Downloads on removable media, portal docs) are only readable on the host.
        """
        iid = (iid or "image").strip().lower() or "image"
        if not ft_layout.is_image_instrument_id(iid):
            self.message.emit(f"Not an Image id: {iid}", True)
            return
        path = resolve_image_source_path(url_or_path)
        if not path:
            self.message.emit("Could not read that file (empty path from the picker)", True)
            return

        def edit(inst):
            inst["id"] = iid
            inst["type"] = "image"
            inst["enabled"] = True

        self._edit_instrument(iid, edit)
        # Always install on the host so /run/media and home paths resolve.
        self._run("Image file", "instrument", "file", iid, path)

    @Slot()
    def addImageInstrument(self):
        """Allocate image / image-N and enable it."""
        self._run("Adding Image", "instrument", "add", "image")

    @Slot(str)
    def removeImageInstrument(self, iid):
        iid = (iid or "").strip().lower()
        if not ft_layout.is_image_instrument_id(iid):
            self.message.emit(f"Not an Image id: {iid}", True)
            return
        self._run("Removing Image", "instrument", "remove", iid)

    @Slot()
    def addLauncherInstrument(self):
        self._run("Adding Launcher", "instrument", "add", "launcher")

    @Slot(str)
    def removeLauncherInstrument(self, iid):
        iid = (iid or "").strip().lower()
        if not ft_layout.is_launcher_instrument_id(iid):
            self.message.emit(f"Not a Launcher id: {iid}", True)
            return
        self._run("Removing Launcher", "instrument", "remove", iid)

    @Slot(str, bool)
    def setLauncherEnabled(self, iid, enabled):
        self._set_instrument_enabled(iid or "launcher", "Launcher", enabled)

    @Slot(str, str)
    def setLauncherAnchor(self, iid, mode):
        self._set_instrument_anchor(iid or "launcher", mode)

    @Slot(str, float)
    def setLauncherMetres(self, iid, metres):
        self._set_instrument_metres(iid or "launcher", metres)

    @Slot(str, float)
    def setLauncherActiveOpacity(self, iid, value):
        self._set_instrument_active_opacity(iid or "launcher", value)

    @Slot(str, float)
    def setLauncherIdleOpacity(self, iid, value):
        self._set_instrument_idle_opacity(iid or "launcher", value)

    @Slot(str, bool)
    def setLauncherAttention(self, iid, enabled):
        self._set_instrument_attention(iid or "launcher", enabled)

    @Slot(str)
    def recenterLauncher(self, iid):
        self._recenter_instrument(iid or "launcher", "Launcher")

    @Slot(str, str)
    def setLauncherDesktop(self, iid, desktop_id):
        iid = (iid or "launcher").strip().lower()
        desktop_id = (desktop_id or "").strip()
        if not desktop_id:
            self.message.emit("Pick an application", True)
            return
        self._run("Setting Launcher app", "instrument", "desktop", iid, desktop_id)

    @Slot(str, str)
    def setLauncherSemantic(self, iid, action):
        iid = (iid or "launcher").strip().lower()
        action = (action or "").strip()
        if not action:
            self.message.emit("Pick a Frametop action", True)
            return
        self._run("Setting Launcher action", "instrument", "semantic", iid, action)

    @Slot(str, str, bool)
    def setLauncherCommand(self, iid, text, shell):
        iid = (iid or "launcher").strip().lower()
        text = (text or "").strip()
        if not text:
            self.message.emit("Enter a command", True)
            return
        if shell:
            self._run("Setting Launcher command", "instrument", "command", iid, "--shell", text)
        else:
            parts = text.split()
            self._run("Setting Launcher command", "instrument", "command", iid, *parts)

    @Slot(str, str, str)
    def setLauncherAppearance(self, iid, mode, extra):
        iid = (iid or "launcher").strip().lower()
        mode = (mode or "app").strip().lower()
        extra = (extra or "").strip()
        args = ["instrument", "appearance", iid, mode]
        if extra:
            args.append(extra)
        self._run("Setting Launcher look", *args)

    @Slot(str, str)
    def setLauncherImageFile(self, iid, url):
        iid = (iid or "launcher").strip().lower()
        path = resolve_image_source_path(url)
        if not path:
            self.message.emit("Could not read that image", True)
            return
        self._run("Launcher image", "instrument", "appearance", iid, "image", path)

    @Slot(str)
    def activateLauncher(self, iid):
        self._run("Activating Launcher", "instrument", "activate", iid or "launcher")

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
    # QApplication (not bare QGuiApplication) so background file picking can use
    # QFileDialog with a reliable start directory (QML portal FileDialog ignores it).
    app = QApplication(sys.argv)
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
