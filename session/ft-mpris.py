#!/usr/bin/env python3
"""Frametop MPRIS bridge: session-bus media → @frametop_mpris for ft-screens.

Runs inside the Frametop nested Plasma session (same private D-Bus as the apps).
ft-screens (in distrobox) talks to the abstract datagram socket @frametop_mpris:

  state                 -> ok <status> <prev> <playpause> <next> <text...>
  playpause|next|previous|play|pause -> ok | error ...

status: playing | paused | stopped | none
prev/playpause/next: 0|1 capability bits
text: "Artist - Title" (ASCII-sanitized) for the marquee; empty when idle.

Dependency-light: prefers gi.repository.Gio; falls back to busctl parsing.
"""
from __future__ import annotations

import argparse
import os
import re
import select
import socket
import subprocess
import sys
import time
import traceback

SOCK_NAME = "\0frametop_mpris"
MPRIS_PREFIX = "org.mpris.MediaPlayer2."
PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
PROPS_IFACE = "org.freedesktop.DBus.Properties"
PLAYER_PATH = "/org/mpris/MediaPlayer2"


def log(*args, **kwargs):
    kwargs.setdefault("flush", True)
    print(*args, **kwargs, file=sys.stderr)


def sanitize_text(s: str, limit: int = 80) -> str:
    if not s:
        return ""
    out = []
    for ch in str(s):
        o = ord(ch)
        if ch in " -_.:'/&+()[]":
            out.append(ch)
        elif 48 <= o <= 57 or 65 <= o <= 90:
            out.append(ch)
        elif 97 <= o <= 122:
            out.append(ch)
        elif ch.isspace():
            out.append(" ")
        # drop other unicode for the ambient glyph font
    text = re.sub(r"\s+", " ", "".join(out)).strip()
    return text[:limit]


def combine_label(artist: str, title: str) -> str:
    artist, title = sanitize_text(artist, 40), sanitize_text(title, 50)
    if artist and title:
        return f"{artist} - {title}"
    return title or artist or ""


class MprisBackend:
    def list_players(self) -> list[str]:
        raise NotImplementedError

    def read_player(self, name: str) -> dict | None:
        raise NotImplementedError

    def call(self, name: str, method: str) -> bool:
        raise NotImplementedError


class GioBackend(MprisBackend):
    def __init__(self):
        from gi.repository import Gio, GLib  # type: ignore

        self.Gio = Gio
        self.GLib = GLib
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    def list_players(self) -> list[str]:
        names = self.bus.call_sync(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "ListNames",
            None,
            None,
            self.Gio.DBusCallFlags.NONE,
            2000,
            None,
        )
        out = []
        for n in names.unpack()[0]:
            if n.startswith(MPRIS_PREFIX) and not n.endswith(".Player"):
                out.append(n)
        return sorted({n for n in out if n.startswith(MPRIS_PREFIX)})

    def _get(self, name: str, prop: str):
        res = self.bus.call_sync(
            name,
            PLAYER_PATH,
            PROPS_IFACE,
            "Get",
            self.GLib.Variant("(ss)", (PLAYER_IFACE, prop)),
            self.GLib.VariantType("(v)"),
            self.Gio.DBusCallFlags.NONE,
            2000,
            None,
        )
        return res.unpack()[0]

    @staticmethod
    def _unwrap(value):
        """Flatten Gio/DBus nested variants into plain Python values."""
        # PyGObject may leave Variant wrappers inside a{sv} maps (Chromium does this).
        unpack = getattr(value, "unpack", None)
        if callable(unpack):
            try:
                return GioBackend._unwrap(unpack())
            except Exception:
                pass
        if isinstance(value, dict):
            return {str(k): GioBackend._unwrap(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [GioBackend._unwrap(v) for v in value]
        return value

    @staticmethod
    def _metadata_map(raw) -> dict:
        raw = GioBackend._unwrap(raw)
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, (list, tuple)):
            # occasional [(k,v), ...] form
            out = {}
            for item in raw:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    out[str(item[0])] = GioBackend._unwrap(item[1])
            return out
        return {}

    def read_player(self, name: str) -> dict | None:
        # Chromium Flatpak publishes MPRIS, but Metadata a{sv} values often stay wrapped
        # as Variants — dict(...) alone then throws and we used to drop the whole player.
        try:
            status = str(self._unwrap(self._get(name, "PlaybackStatus")) or "Stopped")
        except Exception as e:
            log(f"mpris read {name} PlaybackStatus: {e}")
            return None
        meta: dict = {}
        try:
            meta = self._metadata_map(self._get(name, "Metadata"))
        except Exception as e:
            log(f"mpris read {name} Metadata: {e}")
        caps = {"can_prev": False, "can_next": False, "can_play": True, "can_pause": True}
        for key, prop in (
            ("can_prev", "CanGoPrevious"),
            ("can_next", "CanGoNext"),
            ("can_play", "CanPlay"),
            ("can_pause", "CanPause"),
        ):
            try:
                caps[key] = bool(self._unwrap(self._get(name, prop)))
            except Exception:
                pass
        artist = meta.get("xesam:artist")
        if isinstance(artist, (list, tuple)):
            artist = ", ".join(str(a) for a in artist if a)
        elif artist is None:
            artist = ""
        title = meta.get("xesam:title") or ""
        return {
            "name": name,
            "status": status.lower(),
            "artist": str(artist),
            "title": str(title),
            **caps,
        }

    def call(self, name: str, method: str) -> bool:
        try:
            self.bus.call_sync(
                name,
                PLAYER_PATH,
                PLAYER_IFACE,
                method,
                None,
                None,
                self.Gio.DBusCallFlags.NONE,
                2000,
                None,
            )
            return True
        except Exception as e:
            log(f"mpris call {method}: {e}")
            return False


class BusctlBackend(MprisBackend):
    """Fallback when PyGObject is missing; parses busctl --user output."""

    def _run(self, args: list[str], timeout: float = 2.0) -> str:
        env = os.environ.copy()
        p = subprocess.run(
            ["busctl", "--user", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        if p.returncode != 0:
            raise RuntimeError(p.stderr.strip() or p.stdout.strip() or "busctl failed")
        return p.stdout

    def list_players(self) -> list[str]:
        out = self._run(["list"])
        names = []
        for line in out.splitlines():
            parts = line.split()
            if not parts:
                continue
            n = parts[0]
            if n.startswith(MPRIS_PREFIX):
                names.append(n)
        return sorted(set(names))

    def read_player(self, name: str) -> dict | None:
        try:
            st = self._run(
                ["get-property", name, PLAYER_PATH, PLAYER_IFACE, "PlaybackStatus"]
            ).strip()
            # s "Playing"
            m = re.search(r'"([^"]*)"', st)
            status = (m.group(1) if m else "Stopped").lower()
            meta_raw = self._run(
                ["get-property", name, PLAYER_PATH, PLAYER_IFACE, "Metadata"]
            )
            title = ""
            artist = ""
            # Titles may contain spaces / newlines inside the quoted string.
            tm = re.search(r'xesam:title"\s+s\s+"((?:\\.|[^"\\])*)"', meta_raw)
            if not tm:
                tm = re.search(r'xesam:title".*?"((?:\\.|[^"\\])*)"', meta_raw, re.S)
            if tm:
                title = tm.group(1).replace("\\n", " ").replace('\\"', '"')
            am = re.search(r'xesam:artist".*?\[(.*?)\]', meta_raw, re.S)
            if am:
                arts = re.findall(r'"([^"]*)"', am.group(1))
                artist = ", ".join(arts)

            def flag(prop: str) -> bool:
                r = self._run(
                    ["get-property", name, PLAYER_PATH, PLAYER_IFACE, prop]
                ).strip()
                return r.endswith("true") or " b true" in r or r.split()[-1] == "true"

            return {
                "name": name,
                "status": status,
                "artist": artist,
                "title": title,
                "can_prev": flag("CanGoPrevious"),
                "can_next": flag("CanGoNext"),
                "can_play": flag("CanPlay"),
                "can_pause": flag("CanPause"),
            }
        except Exception:
            return None

    def call(self, name: str, method: str) -> bool:
        try:
            self._run(["call", name, PLAYER_PATH, PLAYER_IFACE, method])
            return True
        except Exception as e:
            log(f"busctl call {method}: {e}")
            return False


def open_backend() -> MprisBackend:
    # SteamOS PyGObject exposes D-Bus Variant on GLib (not Gio). Smoke-test before use.
    try:
        from gi.repository import GLib  # type: ignore

        if not hasattr(GLib, "Variant"):
            raise RuntimeError("GLib.Variant missing")
        GLib.Variant("(ss)", ("a", "b"))
        b = GioBackend()
        log("mpris: using Gio backend")
        return b
    except Exception as e:
        log(f"mpris: Gio unavailable ({e}); using busctl")
        return BusctlBackend()


def pick_player(backend: MprisBackend) -> dict | None:
    """Prefer Playing, then Paused, else first readable player."""
    players = backend.list_players()
    paused = None
    any_p = None
    for name in players:
        info = backend.read_player(name)
        if not info:
            continue
        if any_p is None:
            any_p = info
        st = info["status"]
        if st == "playing":
            return info
        if st == "paused" and paused is None:
            paused = info
    return paused or any_p


def format_state(info: dict | None) -> str:
    if not info:
        return "ok none 0 0 0 "
    st = info["status"]
    if st not in ("playing", "paused", "stopped"):
        st = "stopped"
    prev = 1 if info.get("can_prev") else 0
    # PlayPause available if either play or pause is allowed (or always try when active).
    pp = 1 if (info.get("can_play") or info.get("can_pause") or st in ("playing", "paused")) else 0
    nxt = 1 if info.get("can_next") else 0
    text = combine_label(info.get("artist", ""), info.get("title", ""))
    return f"ok {st} {prev} {pp} {nxt} {text}"


def handle(backend: MprisBackend, cmd: str) -> str:
    cmd = (cmd or "").strip()
    if not cmd or cmd == "state":
        return format_state(pick_player(backend))
    method = {
        "playpause": "PlayPause",
        "play": "Play",
        "pause": "Pause",
        "next": "Next",
        "previous": "Previous",
        "prev": "Previous",
    }.get(cmd.lower())
    if not method:
        return f"error unknown command {cmd}"
    info = pick_player(backend)
    if not info:
        return "error no player"
    if backend.call(info["name"], method):
        time.sleep(0.05)
        return format_state(pick_player(backend))
    return "error call failed"


def serve():
    backend = open_backend()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        sock.bind(SOCK_NAME)
    except OSError as e:
        log(f"mpris: bind {SOCK_NAME!r} failed: {e}")
        raise
    sock.setblocking(False)
    log("mpris: listening on @frametop_mpris")
    while True:
        try:
            r, _, _ = select.select([sock], [], [], 1.0)
            if not r:
                continue
            data, addr = sock.recvfrom(4096)
            try:
                reply = handle(backend, data.decode(errors="replace"))
            except Exception as e:
                # Re-open the session bus if Plasma/dbus-run-session recycled it.
                log(f"mpris handle error: {e}")
                try:
                    backend = open_backend()
                    reply = handle(backend, data.decode(errors="replace"))
                except Exception:
                    traceback.print_exc()
                    reply = "error internal"
            if addr:
                try:
                    sock.sendto(reply.encode(), addr)
                except OSError:
                    pass
        except KeyboardInterrupt:
            break


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "cmd",
        nargs="?",
        default="",
        help="serve (default) or one-shot: state|playpause|next|previous|play|pause",
    )
    args = ap.parse_args()
    oneshot = {"state", "playpause", "play", "pause", "next", "previous", "prev"}
    if args.cmd in oneshot:
        print(handle(open_backend(), args.cmd))
        return 0
    if args.cmd and args.cmd not in oneshot:
        log(f"unknown command {args.cmd!r}")
        return 2
    serve()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
