#!/usr/bin/env python3
"""Tests for Launcher Spatial Instrument + FreeDesktop helpers.

Run:
  python3 test/test_launcher_instrument.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "layout"))
import ft_desktop  # noqa: E402
import ft_layout  # noqa: E402


class DesktopDiscovery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.apps = os.path.join(self.tmp.name, "applications")
        os.makedirs(self.apps)

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name, body):
        path = os.path.join(self.apps, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        return path

    def test_parses_name_and_filters_nodisplay(self):
        self._write(
            "ok.desktop",
            "[Desktop Entry]\nType=Application\nName=Ok App\nExec=okapp\nIcon=ok\n",
        )
        self._write(
            "hidden.desktop",
            "[Desktop Entry]\nType=Application\nName=Hidden\nExec=x\nNoDisplay=true\n",
        )
        self._write(
            "notapp.desktop",
            "[Desktop Entry]\nType=Link\nName=Link\nURL=https://example.com\n",
        )
        with mock.patch.object(ft_desktop, "applications_dirs", return_value=[self.apps]):
            apps = ft_desktop.list_applications()
        ids = {a["id"] for a in apps}
        self.assertIn("ok.desktop", ids)
        self.assertNotIn("hidden.desktop", ids)
        self.assertNotIn("notapp.desktop", ids)
        self.assertEqual(apps[0]["name"], "Ok App")

    def test_search_filters_by_name(self):
        self._write(
            "konsole.desktop",
            "[Desktop Entry]\nType=Application\nName=Konsole\nExec=konsole\n",
        )
        self._write(
            "firefox.desktop",
            "[Desktop Entry]\nType=Application\nName=Firefox\nExec=firefox\n",
        )
        with mock.patch.object(ft_desktop, "applications_dirs", return_value=[self.apps]):
            apps = ft_desktop.list_applications(search="kons")
        self.assertEqual([a["id"] for a in apps], ["konsole.desktop"])

    def test_exec_field_codes_stripped_no_shell(self):
        argv = ft_desktop.argv_from_desktop_exec("/usr/bin/foo %f %u --bar")
        self.assertEqual(argv, ["/usr/bin/foo", "--bar"])

    def test_resolve_icon_absolute_png(self):
        png = os.path.join(self.tmp.name, "icon.png")
        with open(png, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n")
        self.assertEqual(ft_desktop.resolve_icon_path(png), png)

    def test_resolve_icon_skips_svg_by_default(self):
        svg = os.path.join(self.tmp.name, "only.svg")
        with open(svg, "w") as f:
            f.write("<svg xmlns='http://www.w3.org/2000/svg'/>")
        self.assertIsNone(ft_desktop.resolve_icon_path(svg))
        self.assertEqual(ft_desktop.resolve_icon_path(svg, allow_svg=True), svg)

    def test_ensure_raster_icon_converts_svg(self):
        svg = os.path.join(self.tmp.name, "app.svg")
        png = os.path.join(self.tmp.name, "out.png")
        with open(svg, "w") as f:
            f.write("<svg xmlns='http://www.w3.org/2000/svg' width='32' height='32'/>")
        # No converter available in many CI images — mock convert_svg_to_png.
        with mock.patch.object(ft_desktop, "convert_svg_to_png", return_value=png) as conv:
            with open(png, "wb") as f:
                f.write(b"\x89PNG\r\n\x1a\n")
            out = ft_desktop.ensure_raster_icon(svg, png, prefer_size=64)
        self.assertEqual(out, png)
        conv.assert_called_once()

    def test_nested_launch_env_rejects_outer_wayland(self):
        runtime = os.path.join(self.tmp.name, "frametop")
        os.makedirs(runtime)
        env_path = os.path.join(runtime, "plasmashell.env")
        # Absolute Wayland path = outer ft-screens (bad).
        blob = (
            b"XDG_RUNTIME_DIR=" + runtime.encode() + b"\0"
            b"WAYLAND_DISPLAY=/run/user/1000/ft-screens-0\0"
        )
        with open(env_path, "wb") as f:
            f.write(blob)
        with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": runtime}, clear=False):
            with self.assertRaises(RuntimeError):
                ft_desktop.nested_launch_env({"XDG_RUNTIME_DIR": runtime})

    def test_nested_launch_env_accepts_wayland_n(self):
        runtime = os.path.join(self.tmp.name, "frametop")
        os.makedirs(runtime)
        env_path = os.path.join(runtime, "plasmashell.env")
        blob = (
            b"XDG_RUNTIME_DIR=" + runtime.encode() + b"\0"
            b"WAYLAND_DISPLAY=wayland-0\0"
            b"DISPLAY=:2\0"
        )
        with open(env_path, "wb") as f:
            f.write(blob)
        env = ft_desktop.nested_launch_env({"XDG_RUNTIME_DIR": runtime, "HOME": self.tmp.name})
        self.assertEqual(env["WAYLAND_DISPLAY"], "wayland-0")
        self.assertEqual(env["XDG_RUNTIME_DIR"], runtime)

    def test_launch_desktop_uses_nested_env(self):
        desk = self._write(
            "demo.desktop",
            "[Desktop Entry]\nType=Application\nName=Demo\nExec=/usr/bin/true\n",
        )
        runtime = os.path.join(self.tmp.name, "frametop")
        os.makedirs(runtime)
        with open(os.path.join(runtime, "plasmashell.env"), "wb") as f:
            f.write(
                b"XDG_RUNTIME_DIR=" + runtime.encode() + b"\0"
                b"WAYLAND_DISPLAY=wayland-0\0"
                b"PATH=/usr/bin\0"
            )
        seen = {}

        def fake_spawn(argv, env=None, cwd=None):
            seen["argv"] = argv
            seen["env"] = env
            return mock.Mock()

        with mock.patch.object(ft_desktop, "applications_dirs", return_value=[self.apps]):
            with mock.patch.object(ft_desktop, "spawn_detached", side_effect=fake_spawn):
                ft_desktop.launch_desktop_id(
                    "demo.desktop",
                    env={"XDG_RUNTIME_DIR": runtime, "PATH": "/usr/bin"},
                )
        self.assertEqual(seen["env"]["WAYLAND_DISPLAY"], "wayland-0")
        self.assertTrue(seen["argv"][0].endswith("true") or seen["argv"][0] == "/usr/bin/true")
        self.assertTrue(os.path.isfile(desk))


class LauncherLayout(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.layout_path = os.path.join(self.tmp.name, "frametop-layout.json")
        self.profiles_path = os.path.join(self.tmp.name, "frametop-layout-profiles.json")
        self.instruments_dir = os.path.join(self.tmp.name, "instruments")
        os.makedirs(self.instruments_dir)
        self._old = (
            ft_layout.LAYOUT_PATH,
            ft_layout.PROFILES_PATH,
            ft_layout.CONF_PATH,
            ft_layout.INSTRUMENTS_DIR,
        )
        ft_layout.LAYOUT_PATH = self.layout_path
        ft_layout.PROFILES_PATH = self.profiles_path
        ft_layout.CONF_PATH = os.path.join(self.tmp.name, "frametop.conf")
        ft_layout.INSTRUMENTS_DIR = self.instruments_dir
        with open(ft_layout.CONF_PATH, "w") as f:
            f.write("BACKEND=screens\n")
        layout = {
            "auto": True,
            "mode": "preset",
            "preset": {"kind": "arc", "rows": 1, "distance": 2.0, "gap": 0.05, "height": 0.0},
            "screens": [{"size": [1920, 1080], "metres": 2.4}],
            "instruments": [],
        }
        ft_layout.save_layout(layout)

    def tearDown(self):
        ft_layout.LAYOUT_PATH, ft_layout.PROFILES_PATH, ft_layout.CONF_PATH, ft_layout.INSTRUMENTS_DIR = self._old
        self.tmp.cleanup()

    def test_multi_launcher_ids(self):
        layout = ft_layout.load_layout()
        self.assertEqual(ft_layout.next_launcher_instrument_id(layout), "launcher")
        layout = ft_layout.upsert_instrument(layout, ft_layout.default_launcher_instrument("launcher"))
        self.assertEqual(ft_layout.next_launcher_instrument_id(layout), "launcher-2")
        layout = ft_layout.upsert_instrument(layout, ft_layout.default_launcher_instrument("launcher-2"))
        ids = [i["id"] for i in ft_layout.instruments_from_layout(layout) if i["type"] == "launcher"]
        self.assertEqual(ids, ["launcher", "launcher-2"])
        self.assertTrue(ft_layout.is_launcher_instrument_id("launcher-3"))
        self.assertFalse(ft_layout.is_launcher_instrument_id("launcher2"))

    def test_coexists_with_clock_battery(self):
        layout = ft_layout.load_layout()
        layout = ft_layout.upsert_instrument(layout, {**ft_layout.default_clock_instrument(), "enabled": True})
        layout = ft_layout.upsert_instrument(layout, {**ft_layout.default_battery_instrument(), "enabled": True})
        layout = ft_layout.upsert_instrument(layout, {
            **ft_layout.default_launcher_instrument("launcher"),
            "enabled": True,
            "desktop_id": "org.kde.konsole.desktop",
        })
        types = {i["type"] for i in ft_layout.instruments_from_layout(layout)}
        self.assertEqual(types, {"clock", "battery", "launcher"})

    def test_action_and_appearance_independent(self):
        raw = {
            **ft_layout.default_launcher_instrument("launcher"),
            "action_kind": "application",
            "desktop_id": "org.kde.konsole.desktop",
            "appearance": "glyph",
            "glyph": "terminal",
            "path": "/tmp/ignored-for-glyph.png",
        }
        inst = ft_layout.normalize_instrument(raw)
        self.assertEqual(inst["action_kind"], "application")
        self.assertEqual(inst["desktop_id"], "org.kde.konsole.desktop")
        self.assertEqual(inst["appearance"], "glyph")
        self.assertEqual(inst["glyph"], "terminal")

    def test_serialization_roundtrip(self):
        layout = ft_layout.load_layout()
        entry = {
            **ft_layout.default_launcher_instrument("launcher-2"),
            "enabled": True,
            "action_kind": "action",
            "semantic": "profile.slot.1",
            "appearance": "glyph",
            "glyph": "star",
            "metres": 0.33,
            "pos": [0.1, 0.2, -1.0],
            "face": [0, 0],
            "roll": 0,
        }
        layout = ft_layout.upsert_instrument(layout, entry)
        ft_layout.save_layout(layout)
        again = ft_layout.instrument_entry(ft_layout.load_layout(), "launcher-2")
        self.assertEqual(again["semantic"], "profile.slot.1")
        self.assertEqual(again["action_kind"], "action")
        self.assertAlmostEqual(again["metres"], 0.33)

    def test_profile_replaces_launcher_set(self):
        # Profile application replaces the full instruments list (documented behavior).
        layout = ft_layout.load_layout()
        layout = ft_layout.upsert_instrument(layout, {
            **ft_layout.default_launcher_instrument("launcher"),
            "enabled": True,
            "desktop_id": "a.desktop",
        })
        layout = ft_layout.upsert_instrument(layout, {
            **ft_layout.default_launcher_instrument("launcher-2"),
            "enabled": True,
            "desktop_id": "b.desktop",
        })
        prof_a = ft_layout.profile_from_layout(layout)
        layout_b = ft_layout.load_layout()
        layout_b["instruments"] = []
        layout_b = ft_layout.upsert_instrument(layout_b, {
            **ft_layout.default_launcher_instrument("launcher"),
            "enabled": True,
            "desktop_id": "c.desktop",
        })
        prof_b = ft_layout.profile_from_layout(layout_b)
        merged = ft_layout.merge_profile_into_layout(layout, prof_b)
        ids = [i["id"] for i in merged["instruments"] if i["type"] == "launcher"]
        self.assertEqual(ids, ["launcher"])
        self.assertEqual(merged["instruments"][0]["desktop_id"], "c.desktop")
        # Old profiles without instruments clear them.
        merged_old = ft_layout.merge_profile_into_layout(layout, {"screens": prof_a["screens"]})
        self.assertEqual(merged_old["instruments"], [])

    def test_old_profiles_still_load(self):
        layout = ft_layout.load_layout()
        layout = ft_layout.upsert_instrument(layout, {**ft_layout.default_clock_instrument(), "enabled": True})
        snap = ft_layout.profile_from_layout(layout)
        # Strip instruments key like a pre-instrument profile.
        old = {"screens": snap["screens"]}
        merged = ft_layout.merge_profile_into_layout(layout, old)
        self.assertEqual(merged["instruments"], [])

    def test_invalid_semantic_rejected_by_normalize_action(self):
        self.assertIsNone(ft_layout.normalize_action("not.a.real.action"))
        self.assertEqual(ft_layout.normalize_action("profile.slot.1"), "profile.slot.1")

    def test_missing_custom_image_keeps_launcher(self):
        inst = ft_layout.normalize_instrument({
            **ft_layout.default_launcher_instrument("launcher"),
            "appearance": "image",
            "path": "/no/such/custom.png",
            "enabled": True,
        })
        self.assertEqual(inst["appearance"], "image")
        self.assertEqual(inst["path"], "/no/such/custom.png")

    def test_command_shell_flag(self):
        inst = ft_layout.normalize_instrument({
            **ft_layout.default_launcher_instrument("launcher"),
            "action_kind": "command",
            "command_shell": True,
            "command": ["echo hello"],
        })
        self.assertTrue(inst["command_shell"])
        self.assertEqual(inst["command"], ["echo hello"])

    def test_spatial_payload_includes_launcher_fields(self):
        snap = ft_layout.spatial_instrument({
            **ft_layout.default_launcher_instrument("launcher"),
            "enabled": True,
            "desktop_id": "org.kde.konsole.desktop",
            "appearance": "app",
            "path": "/tmp/x.png",
        })
        self.assertEqual(snap["type"], "launcher")
        self.assertEqual(snap["desktop_id"], "org.kde.konsole.desktop")
        self.assertEqual(snap["path"], "/tmp/x.png")


class LauncherSourceGuards(unittest.TestCase):
    def test_vr_has_launcher_type_and_no_gaze_activate(self):
        src = (ROOT / "screens" / "vr.cpp").read_text(encoding="utf-8", errors="replace")
        self.assertIn("InstrumentType::Launcher", src)
        self.assertIn("AskFrametopLaunch", src)
        self.assertIn("PollLauncherOverlay", src)
        # Gaze must not call ActivateLauncher.
        start = src.find("void UpdateGaze")
        end = src.find("void UpdateLasers")
        if start > 0 and end > start:
            gaze = src[start:end]
            self.assertNotIn("ActivateLauncher", gaze)

    def test_session_starts_ft_launch(self):
        src = (ROOT / "session" / "frametop-session.sh").read_text(encoding="utf-8", errors="replace")
        self.assertIn("ft-launch.py", src)
        launch = (ROOT / "session" / "ft-launch.py").read_text(encoding="utf-8")
        self.assertIn("frametop_launch", launch)
        self.assertIn("nested_launch_env", launch)
        self.assertIn("plasmashell.env", launch)


if __name__ == "__main__":
    unittest.main()
