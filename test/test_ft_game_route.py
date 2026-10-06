#!/usr/bin/env python3
"""Unit tests for session/ft_game_route.py chooser FSM + classification."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "session"))

import ft_game_route as r  # noqa: E402


class Classify(unittest.TestCase):
    def test_flat(self):
        c, vr = r.classify_launch(launch_options=[
            {"bIsVRLaunchOption": 0},
            {"bIsVRLaunchOption": 0},
        ])
        self.assertEqual(c, "flat")
        self.assertFalse(vr)

    def test_vr_only(self):
        c, vr = r.classify_launch(launch_options=[
            {"bIsVRLaunchOption": 1},
        ])
        self.assertEqual(c, "vr_only")
        self.assertTrue(vr)

    def test_hybrid_selected_vr(self):
        opts = [{"bIsVRLaunchOption": 0}, {"bIsVRLaunchOption": 1}]
        c, vr = r.classify_launch(launch_options=opts, selected_index=1)
        self.assertEqual(c, "hybrid")
        self.assertTrue(vr)

    def test_details_vr_only(self):
        c, vr = r.classify_launch(details={"vr_only": True})
        self.assertEqual(c, "vr_only")
        self.assertTrue(vr)


class FSM(unittest.TestCase):
    def test_cancel_flow(self):
        fsm = r.ChooserFSM()
        ctx = r.LaunchContext(1, "1145360", 1145360, "LaunchApp", 100, name="Hades", classification="flat")
        self.assertEqual(fsm.begin_intercept(ctx), "cancel")
        self.assertTrue(fsm.choose("cancel"))
        self.assertEqual(fsm.state, "done")
        self.assertIsNone(fsm.pending)

    def test_steamvr_bypass(self):
        fsm = r.ChooserFSM()
        ctx = r.LaunchContext(1, "1145360", 1145360, "LaunchApp", 100, classification="flat")
        self.assertEqual(fsm.begin_intercept(ctx), "cancel")
        self.assertTrue(fsm.choose("steamvr"))
        self.assertTrue(fsm.should_bypass("1145360", 1145360))
        self.assertEqual(fsm.begin_intercept(ctx), "ignore")  # consumes bypass
        self.assertFalse(fsm.should_bypass("1145360", 1145360))

    def test_tovakai_desktop_once(self):
        fsm = r.ChooserFSM()
        ctx = r.LaunchContext(1, "1145360", 1145360, "LaunchApp", 100, classification="flat")
        fsm.begin_intercept(ctx)
        fsm.choose("tovakai")
        self.assertTrue(fsm.maybe_fire_desktop_mode())
        self.assertFalse(fsm.maybe_fire_desktop_mode())

    def test_vr_only_skipped(self):
        fsm = r.ChooserFSM()
        ctx = r.LaunchContext(1, "1", 1, "LaunchApp", 100, classification="vr_only")
        self.assertEqual(fsm.begin_intercept(ctx), "ignore")

    def test_steamvr_no_desktop(self):
        fsm = r.ChooserFSM()
        ctx = r.LaunchContext(1, "1145360", 1145360, "LaunchApp", 100, classification="flat")
        fsm.begin_intercept(ctx)
        fsm.choose("steamvr")
        self.assertFalse(fsm.maybe_fire_desktop_mode())


class Marker(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "m.json")
            payload = r.make_marker_payload(app_id=1145360, original="", installed="x %command%", name="Hades")
            r.write_marker(path, payload)
            got = r.read_marker(path)
            self.assertEqual(got["original"], "")
            self.assertTrue(got["pending"])
            r.clear_marker(path)
            self.assertIsNone(r.read_marker(path))


class AppId(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(r.parse_app_id_from_game_id("1145360"), 1145360)


if __name__ == "__main__":
    unittest.main()
