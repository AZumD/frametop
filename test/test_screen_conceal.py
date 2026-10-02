#!/usr/bin/env python3
"""Phase 2: screens hidden one at a time (ft-screens conceal/reveal/concealed).

  - ft-layout: "hidden" in the layout file round-trips through hide/show N|all; bad numbers
    raise; send_hidden pushes conceal/reveal for every screen; apply_screens sends them (and
    "vrkeyboard close") after placing; an ft-screens that doesn't know conceal doesn't break it
  - the `hidden` flag is per screen only: instruments, other screen fields, and the spatial
    profile keys are untouched
  - the CLI: ft-layout hide|show N|all and hidden
  - ft-screens (vr.cpp) and Display Settings wiring, checked in the source

  python3 test/test_screen_conceal.py
"""
from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT / "layout" / "ft_layout.py"


def load_ft_layout():
    spec = importlib.util.spec_from_file_location("ft_layout_conceal", LAYOUT)
    mod = importlib.util.module_from_spec(spec)
    if "fcntl" not in sys.modules:
        sys.modules["fcntl"] = mock.MagicMock()  # Windows unit tests; the Frame has fcntl
    spec.loader.exec_module(mod)
    return mod


class FakeSock:
    """ft-screens' control socket: records asks; `old` answers conceal/reveal like an older build."""

    def __init__(self, old=False):
        self.old = old
        self.cmds = []

    def ask(self, cmd):
        self.cmds.append(cmd)
        word = cmd.split()[0]
        if word in ("conceal", "reveal") and self.old:
            raise RuntimeError("unknown command")
        if cmd == "head":
            return "ok 0.0 1.5 0.0 0.0"
        if cmd == "screens":
            return "ok 3 1:0x1 2:0x2 3:0x3"
        if cmd.startswith("get "):
            return "ok " + " ".join(["0"] * 12) + " 1.0 0.6 0.0 1.0 1.0 world"
        return "ok"


INSTRUMENT = {"id": "clock", "type": "clock", "enabled": True, "metres": 0.25, "active_opacity": 1.0,
              "idle_opacity": 0.4, "color": "#39FF14"}


def base_layout():
    return {
        "auto": True, "mode": "preset",
        "screens": [{"size": [1920, 1080], "metres": 2.4}, {"size": [2560, 1440], "metres": 3.2, "scale": 1.25},
                    {"size": [1920, 1080], "metres": 2.4, "curve": 1.5}],
        "instruments": [dict(INSTRUMENT)],
        "visibility": {"mode": "always"},
    }


class ConcealLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ft = load_ft_layout()

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.path = Path(self.td.name) / "layout.json"
        self.path.write_text(json.dumps(base_layout()))
        self.sock = FakeSock()
        self.patches = [
            mock.patch.object(self.ft, "LAYOUT_PATH", str(self.path)),
            mock.patch.object(self.ft, "backend", return_value="screens"),
            mock.patch.object(self.ft, "screens_socket", side_effect=lambda: self.sock),
            mock.patch.object(self.ft, "log"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.td.cleanup()

    def hidden(self):
        return [bool(s.get("hidden")) for s in json.loads(self.path.read_text())["screens"]]

    # --- file round trip ---
    def test_hide_and_show_one(self):
        self.ft.set_hidden("2", True)
        self.assertEqual(self.hidden(), [False, True, False])
        self.assertEqual(self.sock.cmds, ["conceal 2"])
        self.ft.set_hidden("2", False)
        self.assertEqual(self.hidden(), [False, False, False])
        self.assertNotIn("hidden", json.loads(self.path.read_text())["screens"][1], "shown screens carry no flag")
        self.assertEqual(self.sock.cmds, ["conceal 2", "reveal 2"])

    def test_hide_and_show_all(self):
        self.ft.set_hidden("all", True)
        self.assertEqual(self.hidden(), [True, True, True])
        self.assertEqual(self.sock.cmds, ["conceal 1", "conceal 2", "conceal 3"])
        self.sock.cmds.clear()
        self.ft.set_hidden("all", False)
        self.assertEqual(self.hidden(), [False] * 3)
        self.assertEqual(self.sock.cmds, ["reveal 1", "reveal 2", "reveal 3"])

    def test_bad_screen_numbers(self):
        before = self.path.read_text()
        for which in ("0", "4", "x", "-1", ""):
            with self.assertRaises(RuntimeError, msg=which):
                self.ft.set_hidden(which, True)
        self.assertEqual(self.path.read_text(), before, "a bad number must not touch the file")
        self.assertEqual(self.sock.cmds, [])

    def test_other_fields_and_instruments_unaffected(self):
        self.ft.set_hidden("1", True)  # the first save adds ft-layout's defaults; compare from there
        self.ft.set_hidden("1", False)
        before = json.loads(self.path.read_text())
        self.ft.set_hidden("2", True)
        self.ft.set_hidden("all", True)
        self.ft.set_hidden("all", False)
        after = json.loads(self.path.read_text())
        self.assertEqual(after, before, "hide/show round trip leaves the layout as it was")
        self.ft.set_hidden("1", True)
        mid = json.loads(self.path.read_text())
        self.assertEqual(mid["instruments"], before["instruments"])
        self.assertEqual(mid["visibility"], before["visibility"])
        self.assertEqual([{k: v for k, v in s.items() if k != "hidden"} for s in mid["screens"]],
                         before["screens"])

    def test_saved_when_the_desktop_is_not_running(self):
        with mock.patch.object(self.ft, "screens_socket", side_effect=RuntimeError("not running")):
            self.ft.set_hidden("3", True)  # saved; only logged
        self.assertEqual(self.hidden(), [False, False, True])

    def test_hidden_survives_load_and_a_short_screens_list(self):
        self.ft.set_hidden("1", True)
        self.assertTrue(self.ft.screen_entry(self.ft.load_layout(), 0).get("hidden"))
        self.assertFalse(self.ft.screen_entry(self.ft.load_layout(), 1).get("hidden"))
        # screen_entry beyond the list is {} (no crash): a count larger than the saved list
        self.assertEqual(self.ft.screen_entry(self.ft.load_layout(), 7), {})

    def test_profile_keys_carry_hidden(self):
        self.assertIn("hidden", self.ft.PROFILE_SCREEN_KEYS)
        entry = {"pos": [0, 0, -2], "face": [0, 0], "hidden": True, "metres": 1.5}
        spatial = self.ft.spatial_screen(entry)
        self.assertTrue(spatial.get("hidden"))
        spatial2 = self.ft.spatial_screen({"pos": [0, 0, -2], "face": [0, 0], "metres": 1.5})
        self.assertNotIn("hidden", spatial2)

    # --- ft-screens commands ---
    def test_send_hidden(self):
        layout = base_layout()
        layout["screens"][0]["hidden"] = True
        layout["screens"][2]["hidden"] = True
        self.ft.send_hidden(self.sock, layout)
        self.assertEqual(self.sock.cmds, ["conceal 1", "reveal 2", "conceal 3"])

    def test_send_hidden_with_an_older_ft_screens(self):
        old = FakeSock(old=True)
        layout = base_layout()
        layout["screens"][1]["hidden"] = True
        self.ft.send_hidden(old, layout)  # must not raise
        self.assertEqual(old.cmds, ["reveal 1"], "gives up after the first refusal")

    def _apply(self, sock, layout):
        targets = [{"center": (i, 1.5, -1), "face": (0, 0), "roll": 0, "metres": 1.0, "curve": 0, "pin": None,
                    "opacity": 1.0, "idle_opacity": 1.0, "attention": None, "follow_deadzone": None}
                   for i in range(3)]
        with mock.patch.object(self.ft, "load_layout", return_value=layout), \
             mock.patch.object(self.ft, "screens_socket", return_value=sock), \
             mock.patch.object(self.ft, "screen_pixels", return_value=(1920, 1080)), \
             mock.patch.object(self.ft, "screen_metres", return_value=1.0), \
             mock.patch.object(self.ft, "push_follow_lag"), \
             mock.patch.object(self.ft, "push_slot_state"), \
             mock.patch.object(self.ft, "live_screen_targets", return_value=targets), \
             mock.patch.object(self.ft, "place_screen", side_effect=lambda s, i, *a: s.ask(f"place {i}")), \
             mock.patch.object(self.ft, "apply_opacity"), mock.patch.object(self.ft, "apply_attention"), \
             mock.patch.object(self.ft, "apply_follow_deadzone"), mock.patch.object(self.ft, "apply_pin"):
            return self.ft.apply_screens(wait=0)

    def test_apply_screens_conceals_after_placing_and_closes_the_keyboard(self):
        layout = base_layout()
        layout["screens"][1]["hidden"] = True
        sock = FakeSock()
        self._apply(sock, layout)
        cmds = sock.cmds
        last_place = max(i for i, c in enumerate(cmds) if c.startswith("place "))
        self.assertEqual([c for c in cmds if c.split()[0] in ("conceal", "reveal")],
                         ["reveal 1", "conceal 2", "reveal 3"])
        self.assertGreater(cmds.index("conceal 2"), last_place, "after the screens are placed")
        self.assertIn("vrkeyboard close", cmds)
        self.assertGreater(cmds.index("vrkeyboard close"), cmds.index("conceal 2"))

    def test_apply_screens_survives_an_older_ft_screens(self):
        layout = base_layout()
        layout["screens"][0]["hidden"] = True

        class Older(FakeSock):
            def ask(self, cmd):
                if cmd.startswith("vrkeyboard"):
                    self.cmds.append(cmd)
                    raise RuntimeError("unknown command")
                return super().ask(cmd)

        sock = Older(old=True)
        self.assertEqual(self._apply(sock, layout), ["ok", "ok", "ok"])
        self.assertTrue(any(c.startswith("instrument ") for c in sock.cmds), "instruments are still pushed")

    def test_instruments_pushed_the_same_with_and_without_hidden_screens(self):
        plain, hid = FakeSock(), FakeSock()
        self._apply(plain, base_layout())
        layout = base_layout()
        for s in layout["screens"]:
            s["hidden"] = True
        self._apply(hid, layout)
        pick = lambda cmds: [c for c in cmds if c.startswith("instrument ")]  # noqa: E731
        self.assertTrue(pick(plain.cmds))
        self.assertEqual(pick(plain.cmds), pick(hid.cmds))

    # --- the CLI ---
    def run_cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = self.ft.main(["ft-layout", *args])
        return rc, out.getvalue().strip()

    def test_cli(self):
        self.assertEqual(self.run_cli("hidden"), (0, ""))
        self.assertEqual(self.run_cli("hide", "2"), (0, ""))
        self.assertEqual(self.run_cli("hidden"), (0, "2"))
        self.assertEqual(self.run_cli("hide", "all"), (0, ""))
        self.assertEqual(self.run_cli("hidden"), (0, "1 2 3"))
        self.assertEqual(self.run_cli("show", "1"), (0, ""))
        self.assertEqual(self.run_cli("hidden"), (0, "2 3"))
        self.assertEqual(self.run_cli("show", "all"), (0, ""))
        self.assertEqual(self.run_cli("hidden"), (0, ""))
        self.assertEqual(self.run_cli("hide", "9")[0], 1, "no such screen is an error")
        # `hide`/`show` need exactly one argument, `toggle` still goes to ft-screens
        self.assertEqual(self.run_cli("toggle")[0], 0)
        self.assertIn("toggle", self.sock.cmds)

    def test_usage_text_names_the_commands(self):
        doc = self.ft.__doc__
        for needle in ("ft-layout hide N|all", "ft-layout show N|all", "ft-layout hidden", '"hidden": true'):
            self.assertIn(needle, doc)


class SourceWiring(unittest.TestCase):
    def read(self, rel):
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_vr_cpp(self):
        src = self.read("screens/vr.cpp")
        self.assertIn("bool alone = false;", src)
        self.assertIn("bool visible = s.shown && (shared || s.drag != Drag::None) && !s.alone;", src)
        self.assertLess(src.index('strncmp(cmd, "concealed", 9)'), src.index('"conceal %15s"'),
                        '"concealed" must be matched before "conceal %s" (sscanf\'s space matches nothing)')
        self.assertIn('sscanf(cmd, "reveal %15s", word)', src)
        self.assertLess(src.index('"conceal %15s"'), src.index('!std::strncmp(cmd, "hide", 4)'),
                        "conceal/reveal before the hotkey's hide/show/toggle")
        self.assertIsNone(re.search(r'"hide %', src), "not 'hide N': older builds read hide* as the hotkey")
        self.assertIn("each(word, [&](Screen &s) { s.alone = conceal; });", src)
        # the instruments never look at `alone`
        inst = src[src.index("void UpdateInstrumentVisibility()"):]
        inst = inst[:inst.index("\n}\n")]
        self.assertNotIn("alone", inst)

    def test_vr_cpp_keyboard_wiring(self):
        src = self.read("screens/vr.cpp")
        for needle in ('#include "keyboard.h"', "keyboard::EndDragBy(dev);", "bool SteamInFront()",
                       "void UpdateSteamInFront()", "bool g_keyboardAside", "Mat g_asidePose",
                       "keyboard::Destroy();", "keyboard::Poll(", "if (g_tick % 9 == 0) UpdateSteamInFront();",
                       "&& !ModeVisible()) {", "bool ft_vr_keyboard_show(int index)",
                       "void ft_vr_keyboard_hide(void)", "kKeyboardAhead = 0.7, kKeyboardBelow = 0.35",
                       "keyboard::SetLasers(g_lasers == Lasers::Always"):
            self.assertIn(needle, src, needle)
        shown = src[src.index("bool ft_vr_keyboard_show(int index)"):]
        self.assertIn("!g_vr", shown[:200], "show is guarded with g_vr")
        self.assertIn("if (g_vr) keyboard::Hide();", src)
        self.assertIn("conceal <screen|all> | reveal <screen|all>", src)

    def test_display_settings(self):
        py = self.read("display-settings/ft_display_settings.py")
        self.assertIn("def screensShown(self):", py)
        self.assertIn("def setScreenShown(self, index, shown):", py)
        self.assertIn("ft_layout.set_hidden(str(index + 1), not shown)", py)
        qml = self.read("display-settings/main.qml")
        shown = qml.index('Kirigami.FormData.label: "Screens shown"')
        wrist = qml.index('Kirigami.FormData.label: "Screens on a wrist or head"')
        self.assertLess(shown, wrist, "Shown switches come before the wrist section")
        block = qml[shown:wrist]
        self.assertIn("backend.setScreenShown(index, checked)", block)
        self.assertIn('text: modelData ? "Shown" : "Hidden"', block)
        self.assertNotIn("float", block.lower(), "no floatd wording here")
        self.assertIn("Windows on it stay there", block)

    def test_layout_startup_paths_send_hidden(self):
        src = self.read("layout/ft_layout.py")
        self.assertGreaterEqual(src.count("send_hidden("), 4)  # def + apply_screens + two startup paths


if __name__ == "__main__":
    unittest.main(verbosity=2)
