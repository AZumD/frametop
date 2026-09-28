#!/usr/bin/env python3
"""Offline unit tests for spatial profiles, anchors, and transition helpers.

Run on a machine with Python 3 (Frame host or PC):
  python3 test/test_spatial_profiles.py
"""
import json
import math
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "layout"))
import ft_layout  # noqa: E402


class SpatialHelpers(unittest.TestCase):
    def test_angle_lerp_wraparound(self):
        # 359 -> 1 should travel +2°, landing near 0 at midpoint
        mid = ft_layout.angle_lerp(359.0, 1.0, 0.5)
        self.assertTrue(abs(mid) < 1.0 or abs(mid - 360) < 1.0, mid)
        self.assertAlmostEqual(ft_layout.angle_lerp(10.0, 20.0, 0.5), 15.0)

    def test_ease_in_out_endpoints(self):
        self.assertAlmostEqual(ft_layout.ease_in_out(0), 0.0)
        self.assertAlmostEqual(ft_layout.ease_in_out(1), 1.0)
        self.assertGreater(ft_layout.ease_in_out(0.5), 0.49)
        self.assertLess(ft_layout.ease_in_out(0.5), 0.51)

    def test_pin_anchor_legacy_hand(self):
        self.assertEqual(ft_layout.pin_anchor({"hand": "left", "rel": [0] * 12}), "left")
        self.assertEqual(ft_layout.pin_anchor({"anchor": "head", "rel": [0] * 12}), "head")
        self.assertIsNone(ft_layout.pin_anchor({"hand": "none"}))
        self.assertIsNone(ft_layout.pin_anchor(None))

    def test_make_pin_keeps_legacy_hand(self):
        p = ft_layout.make_pin("right", list(range(12)))
        self.assertEqual(p["anchor"], "right")
        self.assertEqual(p["hand"], "right")
        h = ft_layout.make_pin("head", list(range(12)))
        self.assertEqual(h["anchor"], "head")
        self.assertNotIn("hand", h)


class ProfileStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.layout_path = os.path.join(self.tmp.name, "frametop-layout.json")
        self.profiles_path = os.path.join(self.tmp.name, "frametop-layout-profiles.json")
        self._old_layout = ft_layout.LAYOUT_PATH
        self._old_profiles = ft_layout.PROFILES_PATH
        self._old_conf = ft_layout.CONF_PATH
        ft_layout.LAYOUT_PATH = self.layout_path
        ft_layout.PROFILES_PATH = self.profiles_path
        ft_layout.CONF_PATH = os.path.join(self.tmp.name, "frametop.conf")
        with open(ft_layout.CONF_PATH, "w") as f:
            f.write("BACKEND=screens\n")
        layout = {
            "auto": True,
            "mode": "custom",
            "preset": {"kind": "arc", "rows": 1, "distance": 2.0, "gap": 0.05, "height": 0.0},
            "visibility": {"mode": "always"},
            "primary": 1,
            "screens": [
                {"size": [1920, 1080], "metres": 2.4, "scale": 1.0, "curve": 0,
                 "pos": [0, 0, -2], "face": [0, 0], "roll": 0},
                {"size": [1920, 1080], "metres": 1.2, "scale": 1.25, "curve": 1.5,
                 "pos": [1, 0.2, -1.5], "face": [-20, 5], "roll": 0,
                 "pin": {"anchor": "head", "rel": [float(i) for i in range(12)]}},
            ],
        }
        ft_layout.save_layout(layout)

    def tearDown(self):
        ft_layout.LAYOUT_PATH = self._old_layout
        ft_layout.PROFILES_PATH = self._old_profiles
        ft_layout.CONF_PATH = self._old_conf
        self.tmp.cleanup()

    def test_missing_profiles_is_safe(self):
        store = ft_layout.load_profiles()
        self.assertEqual(store["profiles"], {})
        self.assertIsNone(store["current"])
        # Active layout untouched
        self.assertTrue(os.path.isfile(self.layout_path))

    def test_corrupt_profiles_is_safe(self):
        with open(self.profiles_path, "w") as f:
            f.write("{not-json")
        store = ft_layout.load_profiles()
        self.assertEqual(store["profiles"], {})
        layout = ft_layout.load_layout()
        self.assertEqual(len(layout["screens"]), 2)

    def test_profile_roundtrip_preserves_spatial_not_scale(self):
        layout = ft_layout.load_layout()
        snap = ft_layout.profile_from_layout(layout)
        self.assertEqual(len(snap["screens"]), 2)
        self.assertNotIn("size", snap["screens"][0])
        self.assertNotIn("scale", snap["screens"][0])
        self.assertEqual(snap["screens"][1]["pin"]["anchor"], "head")

        # Mutate active layout scale/size, then merge profile back
        layout["screens"][0]["scale"] = 2.0
        layout["screens"][0]["size"] = [2560, 1440]
        layout["screens"][0]["pos"] = [9, 9, 9]
        merged = ft_layout.merge_profile_into_layout(layout, snap)
        self.assertEqual(merged["screens"][0]["scale"], 2.0)
        self.assertEqual(merged["screens"][0]["size"], [2560, 1440])
        self.assertEqual(merged["screens"][0]["pos"], [0, 0, -2])
        self.assertEqual(merged["screens"][1]["pin"]["anchor"], "head")
        self.assertEqual(merged["mode"], "custom")

    def test_profile_screen_count_mismatch(self):
        layout = ft_layout.load_layout()
        bad = {"screens": [ft_layout.spatial_screen(layout["screens"][0])]}
        with self.assertRaises(RuntimeError):
            ft_layout.merge_profile_into_layout(layout, bad)

    def test_save_apply_delete_via_store(self):
        layout = ft_layout.load_layout()
        store = ft_layout.load_profiles()
        store["profiles"]["Desk"] = ft_layout.profile_from_layout(layout)
        store["current"] = "Desk"
        ft_layout.save_profiles(store)
        loaded = ft_layout.load_profiles()
        self.assertIn("Desk", loaded["profiles"])
        self.assertEqual(loaded["current"], "Desk")
        # delete
        del loaded["profiles"]["Desk"]
        loaded["current"] = None
        ft_layout.save_profiles(loaded)
        self.assertNotIn("Desk", ft_layout.load_profiles()["profiles"])

    def test_parse_get_head_anchor(self):
        # Synthetic get reply with head + 12 rel floats
        rel = " ".join(f"{i:.5f}" for i in range(12))
        reply = ("ok 0.1 0.2 -1.5  1 0 0  0 1 0  0 0 1  2.4000 1.3500 0.000 head " + rel)
        g = ft_layout.parse_get(reply)
        self.assertEqual(g["anchor"], "head")
        self.assertEqual(g["hand"], "head")
        self.assertEqual(len(g["rel"]), 12)


if __name__ == "__main__":
    unittest.main()
