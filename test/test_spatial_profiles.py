#!/usr/bin/env python3
"""Offline unit tests for spatial profiles, anchors, slots, opacity, and transitions.

Run on a machine with Python 3 (Frame host or PC / WSL):
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


def exp_smooth_alpha(dt, tau):
    """Mirrors screens/vr.cpp SmoothToward: a = 1 - exp(-dt/tau)."""
    if tau <= 1e-4 or dt <= 0:
        return 1.0
    return 1.0 - math.exp(-dt / tau)


class SpatialHelpers(unittest.TestCase):
    def test_angle_lerp_wraparound(self):
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
        self.assertEqual(ft_layout.pin_anchor({"hand": "head", "rel": [0] * 12}), "head")
        self.assertEqual(ft_layout.pin_anchor({"hand": "none"}), "world")
        self.assertIsNone(ft_layout.pin_anchor(None))

    def test_legacy_head_is_soft(self):
        # Iteration-1 profiles used hand/anchor "head"; that maps to soft head, not head-rigid.
        self.assertEqual(ft_layout.normalize_anchor("head"), "head")
        self.assertIn("head", ft_layout.SOFT_FOLLOW_ANCHORS)
        self.assertNotEqual(ft_layout.normalize_anchor("head"), "head-rigid")
        pin = ft_layout.make_pin("head", list(range(12)))
        self.assertEqual(pin["anchor"], "head")
        self.assertEqual(pin["hand"], "head")  # kept for iteration-1 readers

    def test_make_pin_keeps_legacy_hand(self):
        p = ft_layout.make_pin("right", list(range(12)))
        self.assertEqual(p["anchor"], "right")
        self.assertEqual(p["hand"], "right")
        for mode in ("yaw-follow", "position-follow", "head-rigid"):
            m = ft_layout.make_pin(mode, list(range(12)))
            self.assertEqual(m["anchor"], mode)
            self.assertNotIn("hand", m)

    def test_anchor_mode_serialization(self):
        for mode in ft_layout.ANCHOR_MODES:
            if mode == "world":
                self.assertIsNone(ft_layout.make_pin(mode, list(range(12))))
            else:
                pin = ft_layout.make_pin(mode, [float(i) for i in range(12)])
                self.assertEqual(ft_layout.pin_anchor(pin), mode)

    def test_default_profile_duration_is_450(self):
        self.assertEqual(ft_layout.DEFAULT_PROFILE_DURATION_MS, 450)
        self.assertEqual(ft_layout.resolve_duration([]), 450.0)
        self.assertEqual(ft_layout.resolve_duration(["--duration", "0"]), 0.0)
        self.assertEqual(ft_layout.resolve_duration(["--duration", "200"]), 200.0)

    def test_follow_smoothing_math(self):
        # ~120 ms tau: after 120 ms, alpha ≈ 1 - 1/e ≈ 0.63
        a = exp_smooth_alpha(0.120, 0.120)
        self.assertAlmostEqual(a, 1.0 - math.exp(-1.0), places=5)
        self.assertEqual(exp_smooth_alpha(0.01, 0.0), 1.0)
        self.assertLess(exp_smooth_alpha(0.016, 0.120), 0.2)

    def test_semantic_action_aliases(self):
        self.assertEqual(ft_layout.normalize_action("profile_slot_2"), "profile.slot.2")
        self.assertEqual(ft_layout.normalize_action("profile.next"), "profile.next")
        self.assertEqual(ft_layout.normalize_action("layout_reset"), "layout.reset")
        self.assertEqual(ft_layout.normalize_action("screens_toggle"), "screens.toggle")
        self.assertIsNone(ft_layout.normalize_action("left"))
        self.assertIsNone(ft_layout.normalize_action(""))
        self.assertIn("profile.slot.1", ft_layout.SEMANTIC_ACTIONS)
        self.assertEqual(len([a for a in ft_layout.SEMANTIC_ACTIONS if a.startswith("profile.slot.")]), 6)


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
            f.write("BACKEND=screens\nFOLLOW_LAG_MS=120\n")
        layout = {
            "auto": True,
            "mode": "custom",
            "preset": {"kind": "arc", "rows": 1, "distance": 2.0, "gap": 0.05, "height": 0.0},
            "visibility": {"mode": "always"},
            "primary": 1,
            "screens": [
                {"size": [1920, 1080], "metres": 2.4, "scale": 1.0, "curve": 0,
                 "pos": [0, 0, -2], "face": [0, 0], "roll": 0, "opacity": 1.0},
                {"size": [1920, 1080], "metres": 1.2, "scale": 1.25, "curve": 1.5,
                 "pos": [1, 0.2, -1.5], "face": [-20, 5], "roll": 0, "opacity": 0.65,
                 "pin": {"hand": "head", "rel": [float(i) for i in range(12)]},
                 "attention": {"enabled": True, "angle": 20, "band": 10, "min": 0.3}},
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
        self.assertEqual(store["slots"], [None] * ft_layout.SLOT_COUNT)
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
        self.assertEqual(snap["screens"][1]["opacity"], 0.65)
        self.assertTrue(snap["screens"][1]["attention"]["enabled"])

        layout["screens"][0]["scale"] = 2.0
        layout["screens"][0]["size"] = [2560, 1440]
        layout["screens"][0]["pos"] = [9, 9, 9]
        layout["screens"][0]["opacity"] = 0.2
        merged = ft_layout.merge_profile_into_layout(layout, snap)
        self.assertEqual(merged["screens"][0]["scale"], 2.0)
        self.assertEqual(merged["screens"][0]["size"], [2560, 1440])
        self.assertEqual(merged["screens"][0]["pos"], [0, 0, -2])
        self.assertEqual(merged["screens"][0]["opacity"], 1.0)
        self.assertEqual(merged["screens"][1]["pin"]["anchor"], "head")
        self.assertEqual(merged["screens"][1]["opacity"], 0.65)
        self.assertEqual(merged["mode"], "custom")

    def test_opacity_defaults_when_absent(self):
        entry = {"pos": [0, 0, -2], "face": [0, 0], "roll": 0, "metres": 2.0, "curve": 0}
        self.assertEqual(ft_layout.screen_opacity(entry), 1.0)
        spatial = ft_layout.spatial_screen({**entry, "size": [1920, 1080], "scale": 1.0})
        self.assertEqual(spatial["opacity"], 1.0)

    def test_opacity_persistence_in_profile(self):
        layout = ft_layout.load_layout()
        layout["screens"][0]["opacity"] = 0.4
        snap = ft_layout.profile_from_layout(layout)
        self.assertEqual(snap["screens"][0]["opacity"], 0.4)
        store = ft_layout.load_profiles()
        store["profiles"]["HUD"] = snap
        ft_layout.save_profiles(store)
        loaded = ft_layout.load_profiles()["profiles"]["HUD"]
        self.assertEqual(loaded["screens"][0]["opacity"], 0.4)

    def test_slot_mapping(self):
        layout = ft_layout.load_layout()
        store = ft_layout.load_profiles()
        store["profiles"]["Desk"] = ft_layout.profile_from_layout(layout)
        store["profiles"]["Cinema"] = ft_layout.profile_from_layout(layout)
        store["current"] = "Desk"
        store["slots"] = ["Desk", None, "Cinema", None, None, None]
        ft_layout.save_profiles(store)
        slots = ft_layout.normalized_slots(ft_layout.load_profiles())
        self.assertEqual(slots[0], "Desk")
        self.assertIsNone(slots[1])
        self.assertEqual(slots[2], "Cinema")
        ft_layout.profile_slot(2, "Desk")
        slots = ft_layout.normalized_slots(ft_layout.load_profiles())
        self.assertEqual(slots[1], "Desk")
        ft_layout.profile_unslot(1)
        slots = ft_layout.normalized_slots(ft_layout.load_profiles())
        self.assertIsNone(slots[0])
        # Unknown names cleared on load
        store = ft_layout.load_profiles()
        store["slots"] = ["Desk", "Missing", "Cinema", None, None, None]
        ft_layout.save_profiles(store)
        slots = ft_layout.normalized_slots(ft_layout.load_profiles())
        self.assertEqual(slots[0], "Desk")
        self.assertIsNone(slots[1])
        self.assertEqual(slots[2], "Cinema")

    def test_run_action_empty_slot_errors(self):
        with self.assertRaises(RuntimeError):
            ft_layout.run_action("profile.slot.1")
        with self.assertRaises(RuntimeError):
            ft_layout.run_action("not.a.real.action")

    def test_legacy_profiles_json_without_slots(self):
        # Iteration-1 file shape: no slots key.
        with open(self.profiles_path, "w") as f:
            json.dump({"current": None, "profiles": {}}, f)
        store = ft_layout.load_profiles()
        self.assertEqual(len(store["slots"]), ft_layout.SLOT_COUNT)
        self.assertTrue(all(s is None for s in store["slots"]))

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
        del loaded["profiles"]["Desk"]
        loaded["current"] = None
        ft_layout.save_profiles(loaded)
        self.assertNotIn("Desk", ft_layout.load_profiles()["profiles"])

    def test_parse_get_head_anchor_with_opacity(self):
        rel = " ".join(f"{i:.5f}" for i in range(12))
        reply = ("ok 0.1 0.2 -1.5  1 0 0  0 1 0  0 0 1  2.4000 1.3500 0.000 0.650 head " + rel)
        g = ft_layout.parse_get(reply)
        self.assertEqual(g["anchor"], "head")
        self.assertEqual(g["hand"], "head")
        self.assertAlmostEqual(g["opacity"], 0.65)
        self.assertEqual(len(g["rel"]), 12)

    def test_parse_get_legacy_without_opacity(self):
        # Older get: ... curve hand [rel] — no opacity field.
        rel = " ".join(f"{i:.5f}" for i in range(12))
        reply = ("ok 0.1 0.2 -1.5  1 0 0  0 1 0  0 0 1  2.4000 1.3500 0.000 head " + rel)
        g = ft_layout.parse_get(reply)
        self.assertEqual(g["anchor"], "head")
        self.assertEqual(g.get("opacity", ft_layout.DEFAULT_OPACITY), ft_layout.DEFAULT_OPACITY)


if __name__ == "__main__":
    unittest.main()
