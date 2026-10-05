#!/usr/bin/env python3
"""Unit tests for session/ft_game_run.py (no Steam/KWin required)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "session"))

import ft_game_run as g  # noqa: E402


class HostRuntime(unittest.TestCase):
    def test_peel_frametop(self):
        self.assertEqual(g.host_runtime_dir({"XDG_RUNTIME_DIR": "/run/user/1000/frametop"}),
                         "/run/user/1000")

    def test_host_passthrough(self):
        self.assertEqual(g.host_runtime_dir({"XDG_RUNTIME_DIR": "/run/user/1000"}),
                         "/run/user/1000")

    def test_env_path(self):
        self.assertEqual(
            g.plasmashell_env_path({"XDG_RUNTIME_DIR": "/run/user/1000"}),
            "/run/user/1000/frametop/plasmashell.env")
        self.assertEqual(
            g.plasmashell_env_path({"XDG_RUNTIME_DIR": "/run/user/1000/frametop"}),
            "/run/user/1000/frametop/plasmashell.env")


class NulEnv(unittest.TestCase):
    def test_load_and_overrides(self):
        blob = b"\0".join([
            b"DISPLAY=:2",
            b"WAYLAND_DISPLAY=wayland-0",
            b"XDG_RUNTIME_DIR=/run/user/1000/frametop",
            b"DBUS_SESSION_BUS_ADDRESS=unix:path=/tmp/dbus-x",
            b"STEAM_FAKE=1",
            b"XAUTHORITY=/run/user/1000/frametop/xauth",
            b"",
        ])
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "plasmashell.env")
            with open(path, "wb") as f:
                f.write(blob)
            loaded = g.load_nul_env_file(path)
            self.assertEqual(loaded["DISPLAY"], ":2")
            self.assertIn("STEAM_FAKE", loaded)
            ov = g.nested_display_overrides(path)
            self.assertEqual(ov["DISPLAY"], ":2")
            self.assertEqual(ov["WAYLAND_DISPLAY"], "wayland-0")
            self.assertEqual(ov["XAUTHORITY"], "/run/user/1000/frametop/xauth")
            self.assertNotIn("DBUS_SESSION_BUS_ADDRESS", ov)
            self.assertNotIn("STEAM_FAKE", ov)

    def test_refuse_bad_wayland(self):
        blob = b"DISPLAY=:2\0WAYLAND_DISPLAY=/run/user/1000/ft-screens-0\0XDG_RUNTIME_DIR=/run/user/1000/frametop\0"
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "plasmashell.env")
            open(path, "wb").write(blob)
            with self.assertRaises(RuntimeError):
                g.nested_display_overrides(path)

    def test_apply_preserves_steam(self):
        base = {"SteamAppId": "1", "DISPLAY": ":1", "PATH": "/usr/bin"}
        out = g.apply_overrides(base, {"DISPLAY": ":2"})
        self.assertEqual(out["SteamAppId"], "1")
        self.assertEqual(out["DISPLAY"], ":2")
        self.assertEqual(base["DISPLAY"], ":1")


class LaunchOptions(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(g.wrap_launch_options("", "/opt/ft-game-run"),
                         "/opt/ft-game-run %command%")

    def test_preserve_mangohud(self):
        self.assertEqual(
            g.wrap_launch_options("mangohud %command%", "/opt/ft-game-run"),
            "/opt/ft-game-run mangohud %command%")

    def test_no_placeholder(self):
        self.assertEqual(
            g.wrap_launch_options("--args", "/opt/ft-game-run"),
            "/opt/ft-game-run %command% --args")

    def test_quote_spaces(self):
        w = g.wrap_launch_options("", "/home/me/My Tools/ft-game-run")
        self.assertTrue(w.startswith("'"))
        self.assertIn("%command%", w)

    def test_already_wrapped(self):
        self.assertTrue(g.already_wrapped("/opt/ft-game-run %command%", "/opt/ft-game-run"))
        self.assertFalse(g.already_wrapped("mangohud %command%", "/opt/ft-game-run"))

    def test_game_id(self):
        self.assertEqual(g.parse_app_id_from_game_id("1145360"), 1145360)
        self.assertEqual(g.parse_app_id_from_game_id(1145360), 1145360)


if __name__ == "__main__":
    unittest.main()
