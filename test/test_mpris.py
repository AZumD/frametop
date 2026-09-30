"""Tests for the MPRIS bridge helpers (session/ft-mpris.py).

Run:
  python3 test/test_mpris.py
"""
from __future__ import annotations

import importlib.util
import os
import socket
import sys
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MPRIS_PATH = ROOT / "session" / "ft-mpris.py"


def load_mpris():
    spec = importlib.util.spec_from_file_location("ft_mpris", MPRIS_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


mpris = load_mpris()


class FakeBackend(mpris.MprisBackend):
    def __init__(self, players=None):
        self.players = list(players or [])
        self.calls = []

    def list_players(self):
        return [p["name"] for p in self.players]

    def read_player(self, name):
        for p in self.players:
            if p["name"] == name:
                return dict(p)
        return None

    def call(self, name, method):
        self.calls.append((name, method))
        for p in self.players:
            if p["name"] != name:
                continue
            if method == "PlayPause":
                p["status"] = "paused" if p["status"] == "playing" else "playing"
            elif method == "Next":
                p["title"] = "Track B"
            elif method == "Previous":
                p["title"] = "Track A"
            return True
        return False


class SanitizeCombine(unittest.TestCase):
    def test_sanitize_ascii(self):
        self.assertEqual(mpris.sanitize_text("Hello World"), "Hello World")
        self.assertEqual(mpris.sanitize_text("Rock ★ Band"), "Rock Band")
        self.assertEqual(mpris.sanitize_text("  multi   space  "), "multi space")
        self.assertEqual(mpris.sanitize_text("A-B_:.'/&+()[]"), "A-B_:.'/&+()[]")

    def test_sanitize_limit(self):
        self.assertEqual(len(mpris.sanitize_text("x" * 200, 80)), 80)

    def test_combine_label(self):
        self.assertEqual(mpris.combine_label("Artist", "Title"), "Artist - Title")
        self.assertEqual(mpris.combine_label("", "Only Title"), "Only Title")
        self.assertEqual(mpris.combine_label("Only Artist", ""), "Only Artist")
        self.assertEqual(mpris.combine_label("", ""), "")


class GioMetadataUnwrap(unittest.TestCase):
    def test_metadata_map_plain(self):
        raw = {"xesam:title": "Song", "xesam:artist": ["A", "B"]}
        meta = mpris.GioBackend._metadata_map(raw)
        self.assertEqual(meta["xesam:title"], "Song")
        self.assertEqual(meta["xesam:artist"], ["A", "B"])

    def test_metadata_map_pairs(self):
        raw = [("xesam:title", "T"), ("xesam:artist", ["X"])]
        meta = mpris.GioBackend._metadata_map(raw)
        self.assertEqual(meta["xesam:title"], "T")

    def test_read_player_survives_bad_metadata(self):
        class Boom(mpris.GioBackend):
            def __init__(self):
                pass

            def _get(self, name, prop):
                if prop == "PlaybackStatus":
                    return "Paused"
                if prop == "Metadata":
                    raise RuntimeError("bad meta")
                if prop.startswith("Can"):
                    return True
                raise RuntimeError(prop)

        info = Boom().read_player("org.mpris.MediaPlayer2.chromium.instance2")
        self.assertIsNotNone(info)
        self.assertEqual(info["status"], "paused")
        self.assertEqual(info["title"], "")
        self.assertTrue(info["can_play"])


class FormatState(unittest.TestCase):
    def test_none(self):
        self.assertEqual(mpris.format_state(None), "ok none 0 0 0 ")

    def test_playing(self):
        info = {
            "status": "playing",
            "artist": "A",
            "title": "B",
            "can_prev": True,
            "can_next": True,
            "can_play": True,
            "can_pause": True,
        }
        self.assertEqual(mpris.format_state(info), "ok playing 1 1 1 A - B")

    def test_paused_caps(self):
        info = {
            "status": "paused",
            "artist": "",
            "title": "Solo",
            "can_prev": False,
            "can_next": True,
            "can_play": True,
            "can_pause": False,
        }
        self.assertEqual(mpris.format_state(info), "ok paused 0 1 1 Solo")


class PickPlayer(unittest.TestCase):
    def test_prefer_playing(self):
        backend = FakeBackend([
            {"name": "org.mpris.MediaPlayer2.a", "status": "paused", "artist": "", "title": "P",
             "can_prev": True, "can_next": True, "can_play": True, "can_pause": True},
            {"name": "org.mpris.MediaPlayer2.b", "status": "playing", "artist": "X", "title": "Y",
             "can_prev": True, "can_next": True, "can_play": True, "can_pause": True},
        ])
        picked = mpris.pick_player(backend)
        self.assertEqual(picked["name"], "org.mpris.MediaPlayer2.b")
        self.assertEqual(picked["status"], "playing")

    def test_paused_when_none_playing(self):
        backend = FakeBackend([
            {"name": "org.mpris.MediaPlayer2.a", "status": "stopped", "artist": "", "title": "S",
             "can_prev": False, "can_next": False, "can_play": True, "can_pause": False},
            {"name": "org.mpris.MediaPlayer2.b", "status": "paused", "artist": "", "title": "P",
             "can_prev": True, "can_next": True, "can_play": True, "can_pause": True},
        ])
        picked = mpris.pick_player(backend)
        self.assertEqual(picked["status"], "paused")


class HandleCommands(unittest.TestCase):
    def test_state_and_playpause(self):
        backend = FakeBackend([
            {"name": "org.mpris.MediaPlayer2.x", "status": "playing", "artist": "A", "title": "T",
             "can_prev": True, "can_next": True, "can_play": True, "can_pause": True},
        ])
        self.assertTrue(mpris.handle(backend, "state").startswith("ok playing"))
        out = mpris.handle(backend, "playpause")
        self.assertTrue(out.startswith("ok paused"))
        self.assertEqual(backend.calls, [("org.mpris.MediaPlayer2.x", "PlayPause")])

    def test_next_previous(self):
        backend = FakeBackend([
            {"name": "org.mpris.MediaPlayer2.x", "status": "playing", "artist": "", "title": "Track A",
             "can_prev": True, "can_next": True, "can_play": True, "can_pause": True},
        ])
        self.assertIn("Track B", mpris.handle(backend, "next"))
        self.assertIn("Track A", mpris.handle(backend, "previous"))

    def test_unknown_and_no_player(self):
        self.assertTrue(mpris.handle(FakeBackend(), "wat").startswith("error unknown"))
        self.assertEqual(mpris.handle(FakeBackend(), "playpause"), "error no player")


class SocketRoundtrip(unittest.TestCase):
    def test_dgram_state(self):
        """Exercise the same reply path as serve() over an abstract datagram socket."""
        if sys.platform == "win32":
            self.skipTest("abstract AF_UNIX sockets are Linux-only")
        sock_name = f"\0ft_mpris_t{os.getpid()}_{int(time.time() * 1000) % 100000}"
        backend = FakeBackend([
            {"name": "org.mpris.MediaPlayer2.t", "status": "playing", "artist": "Artist",
             "title": "Song", "can_prev": True, "can_next": False, "can_play": True, "can_pause": True},
        ])
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            srv.bind(sock_name)
        except OSError as e:
            self.skipTest(f"abstract unix sockets unavailable: {e}")
            return
        srv.settimeout(2.0)
        err = {"e": None}

        def serve_once():
            try:
                data, addr = srv.recvfrom(4096)
                reply = mpris.handle(backend, data.decode())
                if addr:
                    srv.sendto(reply.encode(), addr)
            except Exception as e:
                err["e"] = e

        t = threading.Thread(target=serve_once, daemon=True)
        t.start()
        cli = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        cli.settimeout(2.0)
        try:
            # Abstract autobind so the server has a reply address.
            cli.bind("\0")
            cli.sendto(b"state", sock_name)
            reply, _ = cli.recvfrom(4096)
            self.assertEqual(reply.decode(), "ok playing 1 1 0 Artist - Song")
        finally:
            cli.close()
            srv.close()
            t.join(timeout=2)
        if err["e"]:
            raise err["e"]


if __name__ == "__main__":
    unittest.main()
