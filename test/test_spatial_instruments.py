#!/usr/bin/env python3
"""Tests for Spatial Instruments layout/profile plumbing (Clock POC).

Run:
  python3 test/test_spatial_instruments.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "layout"))
import ft_layout  # noqa: E402


class SpatialInstrumentsLayout(unittest.TestCase):
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
            "screens": [
                {"size": [1920, 1080], "metres": 2.4, "scale": 1.0, "curve": 0,
                 "pos": [0, 0, -2], "face": [0, 0], "roll": 0, "opacity": 1.0},
            ],
        }
        ft_layout.save_layout(layout)

    def tearDown(self):
        ft_layout.LAYOUT_PATH = self._old_layout
        ft_layout.PROFILES_PATH = self._old_profiles
        ft_layout.CONF_PATH = self._old_conf
        self.tmp.cleanup()

    def test_old_layout_without_instruments_loads(self):
        layout = ft_layout.load_layout()
        self.assertEqual(ft_layout.instruments_from_layout(layout), [])
        self.assertEqual(len(layout["screens"]), 1)

    def test_old_profile_without_instruments_clears(self):
        layout = ft_layout.load_layout()
        layout = ft_layout.upsert_instrument(layout, {
            **ft_layout.default_clock_instrument(),
            "enabled": True,
            "pos": [0, 0.2, -1],
            "face": [0, 0],
            "roll": 0,
        })
        ft_layout.save_layout(layout)
        old_profile = {"screens": [ft_layout.spatial_screen(layout["screens"][0])]}
        merged = ft_layout.merge_profile_into_layout(layout, old_profile)
        self.assertEqual(merged["instruments"], [])

    def test_clock_roundtrip_layout(self):
        layout = ft_layout.load_layout()
        clock = ft_layout.default_clock_instrument()
        clock.update({
            "enabled": True,
            "metres": 0.4,
            "active_opacity": 1.0,
            "idle_opacity": 0.2,
            "pos": [0.1, 0.15, -1.0],
            "face": [5.0, 0.0],
            "roll": 0.0,
            "pin": {"anchor": "yaw-follow", "rel": [float(i) for i in range(12)]},
            "attention": {"enabled": True, "in_ms": 100, "out_ms": 200},
        })
        layout = ft_layout.upsert_instrument(layout, clock)
        ft_layout.save_layout(layout)
        loaded = ft_layout.load_layout()
        items = ft_layout.instruments_from_layout(loaded)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "clock")
        self.assertTrue(items[0]["enabled"])
        self.assertEqual(items[0]["metres"], 0.4)
        self.assertEqual(items[0]["idle_opacity"], 0.2)
        self.assertEqual(ft_layout.pin_anchor(items[0]["pin"]), "yaw-follow")
        self.assertTrue(items[0]["attention"]["enabled"])

    def test_profile_roundtrip_clock(self):
        layout = ft_layout.load_layout()
        clock = ft_layout.default_clock_instrument()
        clock.update({"enabled": True, "pos": [0, 0.2, -1], "face": [0, 0], "roll": 0,
                      "idle_opacity": 0.3, "active_opacity": 0.9})
        layout = ft_layout.upsert_instrument(layout, clock)
        snap = ft_layout.profile_from_layout(layout)
        self.assertEqual(len(snap["instruments"]), 1)
        self.assertEqual(snap["instruments"][0]["type"], "clock")
        self.assertTrue(snap["instruments"][0]["enabled"])

        layout2 = ft_layout.load_layout()
        layout2["instruments"] = []
        merged = ft_layout.merge_profile_into_layout(layout2, snap)
        self.assertEqual(len(merged["instruments"]), 1)
        self.assertAlmostEqual(merged["instruments"][0]["idle_opacity"], 0.3)

    def test_unknown_instrument_type_safe(self):
        bad = {"id": "x", "type": "weather-orb", "enabled": True}
        self.assertIsNone(ft_layout.normalize_instrument(bad, warn=False))
        layout = ft_layout.load_layout()
        layout["instruments"] = [bad, ft_layout.default_clock_instrument()]
        items = ft_layout.instruments_from_layout(layout)
        self.assertEqual([i["id"] for i in items], ["clock"])

    def test_enable_disable(self):
        layout = ft_layout.upsert_instrument(ft_layout.load_layout(), {
            **ft_layout.default_clock_instrument(), "enabled": True})
        self.assertTrue(ft_layout.instrument_entry(layout, "clock")["enabled"])
        layout = ft_layout.upsert_instrument(layout, {
            **ft_layout.instrument_entry(layout, "clock"), "enabled": False})
        self.assertFalse(ft_layout.instrument_entry(layout, "clock")["enabled"])

    def test_profile_switch_clock_states(self):
        layout = ft_layout.load_layout()
        a = ft_layout.upsert_instrument(layout, {
            **ft_layout.default_clock_instrument(),
            "enabled": True, "pos": [0, 0.2, -1], "face": [0, 0], "idle_opacity": 0.2,
        })
        snap_a = ft_layout.profile_from_layout(a)
        b = ft_layout.upsert_instrument(layout, {
            **ft_layout.default_clock_instrument(),
            "enabled": False, "pos": [0.5, 0.1, -1.2], "face": [10, 0], "idle_opacity": 0.5,
        })
        snap_b = ft_layout.profile_from_layout(b)
        store = {"current": None, "profiles": {"A": snap_a, "B": snap_b}, "slots": [None] * 6}
        ft_layout.save_profiles(store)

        merged_a = ft_layout.merge_profile_into_layout(ft_layout.load_layout(), snap_a)
        merged_b = ft_layout.merge_profile_into_layout(ft_layout.load_layout(), snap_b)
        self.assertTrue(merged_a["instruments"][0]["enabled"])
        self.assertAlmostEqual(merged_a["instruments"][0]["idle_opacity"], 0.2)
        self.assertFalse(merged_b["instruments"][0]["enabled"])
        self.assertAlmostEqual(merged_b["instruments"][0]["idle_opacity"], 0.5)

    def test_malformed_instruments_field(self):
        layout = ft_layout.load_layout()
        layout["instruments"] = "nope"
        self.assertEqual(ft_layout.instruments_from_layout(layout), [])


if __name__ == "__main__":
    unittest.main()
