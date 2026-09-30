#!/usr/bin/env python3
"""apply_screens must push visibility / instruments even when head pose is missing.

Desktop start often races SteamVR: ft-screens is up before the HMD reports a pose.
A failed `head` used to abort apply entirely, leaving visibility at `always`,
outputScale at 1.0 (pointer misaligned after KWin scale), and no instruments.

Run:
  python3 test/test_apply_without_head.py
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT / "layout" / "ft_layout.py"


def load_ft_layout():
    spec = importlib.util.spec_from_file_location("ft_layout", LAYOUT)
    mod = importlib.util.module_from_spec(spec)
    # Avoid importing real fcntl on Windows; stub before exec.
    if "fcntl" not in sys.modules:
        sys.modules["fcntl"] = mock.MagicMock()
    spec.loader.exec_module(mod)
    return mod


class FakeSock:
    def __init__(self, *, head_ok=False):
        self.head_ok = head_ok
        self.cmds = []

    def ask(self, cmd):
        self.cmds.append(cmd)
        if cmd == "head":
            if not self.head_ok:
                raise RuntimeError("no HMD")
            return "ok 0.1 1.5 -0.2 10.0"
        if cmd == "screens":
            return "ok 2 1:0x1 2:0x2"
        if cmd.startswith("get "):
            # pose (12) + metres height curve + opacity idle anchor
            return "ok " + " ".join(["0"] * 12) + " 1.0 0.6 0.0 1.0 1.0 world"
        if cmd.startswith("instrument"):
            return "ok"
        if cmd.split()[0] in (
            "place", "visibility", "wrist", "gesture", "controllers", "ingames",
            "follow", "opacity", "attention", "deadzone", "unpin", "pin",
        ):
            return "ok"
        return "ok"


class ApplyWithoutHead(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ft = load_ft_layout()

    def test_read_head_pose_none(self):
        sock = FakeSock(head_ok=False)
        self.assertIsNone(self.ft.read_head_pose(sock, retries=1, delay=0))

    def test_read_head_pose_ok(self):
        sock = FakeSock(head_ok=True)
        eye, yaw = self.ft.read_head_pose(sock)
        self.assertEqual(eye, (0.1, 1.5, -0.2))
        self.assertEqual(yaw, 10.0)

    def test_apply_screens_sends_visibility_without_head(self):
        sock = FakeSock(head_ok=False)
        layout = {
            "screens": [{"metres": 1.0}, {"metres": 1.0}],
            "visibility": {
                "mode": "except_dashboard",
                "wrist_angle": 60,
                "gesture_hand": "left",
                "gesture_angle": 20,
                "controllers": "hide",
                "in_games": "hide",
            },
            "instruments": [
                {"id": "clock", "type": "clock", "enabled": True,
                 "metres": 0.25, "active_opacity": 1.0, "idle_opacity": 0.4,
                 "color": "#39FF14"},
            ],
            "auto": True,
        }

        with tempfile.TemporaryDirectory() as td:
            layout_path = Path(td) / "layout.json"
            with mock.patch.object(self.ft, "LAYOUT_PATH", layout_path), \
                 mock.patch.object(self.ft, "load_layout", return_value=layout), \
                 mock.patch.object(self.ft, "screens_socket", return_value=sock), \
                 mock.patch.object(self.ft, "backend", return_value="screens"), \
                 mock.patch.object(self.ft, "screen_pixels", return_value=(1920, 1080)), \
                 mock.patch.object(self.ft, "screen_metres", return_value=1.0), \
                 mock.patch.object(self.ft, "push_follow_lag"), \
                 mock.patch.object(self.ft, "push_slot_state"), \
                 mock.patch.object(self.ft, "log"):
                # place_screen / live targets need a bit more — stub place path
                with mock.patch.object(self.ft, "live_screen_targets",
                                       return_value=[
                                           {"center": (0, 1.5, -1), "face": (0, 0), "roll": 0,
                                            "metres": 1.0, "curve": 0, "pin": None,
                                            "opacity": 1.0, "idle_opacity": 1.0,
                                            "attention": None, "follow_deadzone": None},
                                           {"center": (1, 1.5, -1), "face": (0, 0), "roll": 0,
                                            "metres": 1.0, "curve": 0, "pin": None,
                                            "opacity": 1.0, "idle_opacity": 1.0,
                                            "attention": None, "follow_deadzone": None},
                                       ]), \
                     mock.patch.object(self.ft, "place_screen", return_value="ok"), \
                     mock.patch.object(self.ft, "apply_opacity"), \
                     mock.patch.object(self.ft, "apply_attention"), \
                     mock.patch.object(self.ft, "apply_follow_deadzone"), \
                     mock.patch.object(self.ft, "apply_pin"):
                    results = self.ft.apply_screens(wait=0)

        self.assertEqual(results, ["ok", "ok"])
        vis = [c for c in sock.cmds if c.startswith("visibility ")]
        self.assertTrue(vis, "visibility must be sent even without head pose")
        self.assertEqual(vis[0], "visibility except_dashboard")
        inst = [c for c in sock.cmds if c.startswith("instrument ")]
        self.assertTrue(any("enable clock" in c or c == "instrument clear" for c in inst),
                        f"instruments must be pushed; got {inst}")

    def test_apply_instruments_fallback_origin(self):
        sock = FakeSock(head_ok=False)
        layout = {
            "instruments": [
                {"id": "clock", "type": "clock", "enabled": True,
                 "metres": 0.25, "active_opacity": 1.0, "idle_opacity": 0.4,
                 "color": "#39FF14", "pos": (0.0, 0.0, -0.5), "face": (0.0, 0.0)},
            ],
        }
        with mock.patch.object(self.ft, "backend", return_value="screens"), \
             mock.patch.object(self.ft, "log"):
            self.ft.apply_instruments(sock, layout)
        self.assertIn("instrument clear", sock.cmds)
        self.assertTrue(any(c.startswith("instrument enable clock") for c in sock.cmds))
        place = [c for c in sock.cmds if c.startswith("instrument place clock")]
        self.assertTrue(place, "place should use fallback eye when head missing")


if __name__ == "__main__":
    unittest.main()
