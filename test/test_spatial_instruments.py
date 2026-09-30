"""Tests for Spatial Instruments layout/profile plumbing (Clock + Battery + Storage + SD + Date + Media).

Run:
  python3 test/test_spatial_instruments.py
"""
from __future__ import annotations

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

    def test_battery_roundtrip_layout(self):
        layout = ft_layout.load_layout()
        bat = ft_layout.default_battery_instrument()
        bat.update({
            "enabled": True,
            "metres": 0.28,
            "idle_opacity": 0.15,
            "active_opacity": 0.95,
            "pos": [-0.2, 0.1, -1.1],
            "face": [0, 0],
            "roll": 0,
            "pin": {"anchor": "position-follow", "rel": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0]},
        })
        layout = ft_layout.upsert_instrument(layout, bat)
        ft_layout.save_layout(layout)
        items = ft_layout.instruments_from_layout(ft_layout.load_layout())
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["type"], "battery")
        self.assertEqual(items[0]["id"], "battery")
        self.assertTrue(items[0]["enabled"])
        self.assertEqual(items[0]["metres"], 0.28)
        self.assertEqual(ft_layout.pin_anchor(items[0]["pin"]), "position-follow")

    def test_storage_and_sd_roundtrip(self):
        layout = ft_layout.load_layout()
        layout = ft_layout.upsert_instrument(layout, {
            **ft_layout.default_storage_instrument(),
            "enabled": True, "metres": 0.3, "pos": [0.1, 0, -1], "face": [0, 0], "roll": 0,
        })
        layout = ft_layout.upsert_instrument(layout, {
            **ft_layout.default_sd_instrument(),
            "enabled": True, "metres": 0.3, "pos": [-0.1, 0, -1], "face": [0, 0], "roll": 0,
            "pin": {"anchor": "yaw-follow", "rel": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0]},
        })
        ft_layout.save_layout(layout)
        by_id = {i["id"]: i for i in ft_layout.instruments_from_layout(ft_layout.load_layout())}
        self.assertEqual(set(by_id), {"storage", "sd"})
        self.assertTrue(by_id["storage"]["enabled"])
        self.assertEqual(ft_layout.pin_anchor(by_id["sd"]["pin"]), "yaw-follow")

    def test_date_roundtrip(self):
        layout = ft_layout.load_layout()
        layout = ft_layout.upsert_instrument(layout, {
            **ft_layout.default_date_instrument(),
            "enabled": True, "metres": 0.4, "pos": [0, 0.25, -1], "face": [0, 0], "roll": 0,
            "pin": {"anchor": "yaw-follow", "rel": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0]},
        })
        ft_layout.save_layout(layout)
        items = ft_layout.instruments_from_layout(ft_layout.load_layout())
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["type"], "date")
        self.assertEqual(items[0]["metres"], 0.4)
        self.assertEqual(ft_layout.pin_anchor(items[0]["pin"]), "yaw-follow")

    def test_media_roundtrip(self):
        layout = ft_layout.load_layout()
        layout = ft_layout.upsert_instrument(layout, {
            **ft_layout.default_media_instrument(),
            "enabled": True, "metres": 0.45, "pos": [0.1, 0.2, -1], "face": [0, 0], "roll": 0,
            "pin": {"anchor": "position-follow", "rel": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0]},
            "idle_opacity": 0.25,
        })
        ft_layout.save_layout(layout)
        items = ft_layout.instruments_from_layout(ft_layout.load_layout())
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["type"], "media")
        self.assertEqual(items[0]["id"], "media")
        self.assertEqual(items[0]["metres"], 0.45)
        self.assertAlmostEqual(items[0]["idle_opacity"], 0.25)
        self.assertEqual(ft_layout.pin_anchor(items[0]["pin"]), "position-follow")
        self.assertIn("media", ft_layout.KNOWN_INSTRUMENT_TYPES)
        self.assertEqual(ft_layout.default_instrument("media")["type"], "media")
        self.assertAlmostEqual(ft_layout.DEFAULT_MEDIA_METRES, 0.42)

    def test_instrument_color_roundtrip(self):
        layout = ft_layout.load_layout()
        layout = ft_layout.upsert_instrument(layout, {
            **ft_layout.default_clock_instrument(),
            "enabled": True, "color": "#ffb84d", "pos": [0, 0.2, -1], "face": [0, 0], "roll": 0,
        })
        layout = ft_layout.upsert_instrument(layout, {
            **ft_layout.default_date_instrument(),
            "enabled": True, "color": "7EC8FF", "pos": [0.2, 0.2, -1], "face": [0, 0], "roll": 0,
        })
        layout = ft_layout.upsert_instrument(layout, {
            **ft_layout.default_battery_instrument(),
            "enabled": True, "color": "#bogus", "pos": [0.4, 0.2, -1], "face": [0, 0], "roll": 0,
        })
        ft_layout.save_layout(layout)
        by_id = {i["id"]: i for i in ft_layout.instruments_from_layout(ft_layout.load_layout())}
        self.assertEqual(by_id["clock"]["color"], "#FFB84D")
        self.assertEqual(by_id["date"]["color"], "#7EC8FF")
        self.assertEqual(by_id["battery"]["color"], ft_layout.DEFAULT_INSTRUMENT_COLOR)
        self.assertEqual(ft_layout.normalize_instrument_color("abc"), ft_layout.DEFAULT_INSTRUMENT_COLOR)
        snap = ft_layout.profile_from_layout(ft_layout.load_layout())
        colors = {i["id"]: i.get("color") for i in snap["instruments"]}
        self.assertEqual(colors["clock"], "#FFB84D")
        self.assertEqual(colors["date"], "#7EC8FF")
        self.assertNotIn("media", colors)  # media was not added in this test
        # Storage type never stores a colour field
        stor = ft_layout.spatial_instrument(ft_layout.default_storage_instrument())
        self.assertNotIn("color", stor)

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

    def test_clock_and_battery_coexist(self):
        layout = ft_layout.load_layout()
        layout = ft_layout.upsert_instrument(layout, {
            **ft_layout.default_clock_instrument(),
            "enabled": True, "pos": [0, 0.2, -1], "face": [0, 0], "roll": 0,
            "pin": {"anchor": "yaw-follow", "rel": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0]},
        })
        layout = ft_layout.upsert_instrument(layout, {
            **ft_layout.default_battery_instrument(),
            "enabled": True, "pos": [0.3, 0.1, -1], "face": [0, 0], "roll": 0,
            "pin": {"anchor": "position-follow", "rel": [0, 0, 1, 0, 0, 1, 0, 0, -1, 0, 0, 0]},
        })
        ft_layout.save_layout(layout)
        items = ft_layout.instruments_from_layout(ft_layout.load_layout())
        by_id = {i["id"]: i for i in items}
        self.assertEqual(set(by_id), {"clock", "battery"})
        self.assertEqual(ft_layout.pin_anchor(by_id["clock"]["pin"]), "yaw-follow")
        self.assertEqual(ft_layout.pin_anchor(by_id["battery"]["pin"]), "position-follow")

    def test_independent_enable_in_profiles(self):
        layout = ft_layout.load_layout()
        work = ft_layout.upsert_instrument(layout, {
            **ft_layout.default_clock_instrument(), "enabled": True, "pos": [0, 0.2, -1],
            "face": [0, 0], "roll": 0,
        })
        work = ft_layout.upsert_instrument(work, {
            **ft_layout.default_battery_instrument(), "enabled": True, "pos": [0.2, 0.1, -1],
            "face": [0, 0], "roll": 0,
            "pin": {"anchor": "position-follow", "rel": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0]},
        })
        snap_work = ft_layout.profile_from_layout(work)

        cinema = ft_layout.upsert_instrument(layout, {
            **ft_layout.default_clock_instrument(), "enabled": False, "pos": [0, 0.2, -1],
            "face": [0, 0], "roll": 0,
        })
        cinema = ft_layout.upsert_instrument(cinema, {
            **ft_layout.default_battery_instrument(), "enabled": True, "pos": [-0.4, 0.0, -1.2],
            "face": [15, 0], "roll": 0,
        })
        snap_cinema = ft_layout.profile_from_layout(cinema)

        m_work = ft_layout.merge_profile_into_layout(ft_layout.load_layout(), snap_work)
        m_cin = ft_layout.merge_profile_into_layout(ft_layout.load_layout(), snap_cinema)
        w = {i["id"]: i for i in m_work["instruments"]}
        c = {i["id"]: i for i in m_cin["instruments"]}
        self.assertTrue(w["clock"]["enabled"])
        self.assertTrue(w["battery"]["enabled"])
        self.assertFalse(c["clock"]["enabled"])
        self.assertTrue(c["battery"]["enabled"])
        self.assertEqual(ft_layout.pin_anchor(w["battery"].get("pin")), "position-follow")
        self.assertIsNone(c["battery"].get("pin"))
        self.assertEqual(c["battery"]["pos"], [-0.4, 0.0, -1.2])

    def test_clock_only_profile_still_loads(self):
        layout = ft_layout.load_layout()
        layout = ft_layout.upsert_instrument(layout, {
            **ft_layout.default_clock_instrument(), "enabled": True,
            "pos": [0, 0.2, -1], "face": [0, 0], "roll": 0,
        })
        layout = ft_layout.upsert_instrument(layout, {
            **ft_layout.default_battery_instrument(), "enabled": True,
            "pos": [0.2, 0, -1], "face": [0, 0], "roll": 0,
        })
        clock_only = {
            "screens": [ft_layout.spatial_screen(layout["screens"][0])],
            "instruments": [ft_layout.spatial_instrument({
                **ft_layout.default_clock_instrument(), "enabled": True,
                "pos": [0, 0.3, -1], "face": [0, 0], "roll": 0,
            })],
        }
        merged = ft_layout.merge_profile_into_layout(layout, clock_only)
        ids = [i["id"] for i in merged["instruments"]]
        self.assertEqual(ids, ["clock"])
        self.assertTrue(merged["instruments"][0]["enabled"])


class BatterySegmentsAndSysfs(unittest.TestCase):
    def test_segment_boundaries(self):
        cases = {
            0: 0,
            1: 1, 20: 1,
            21: 2, 40: 2,
            41: 3, 60: 3,
            61: 4, 80: 4,
            81: 5, 100: 5,
        }
        for pct, segs in cases.items():
            self.assertEqual(ft_layout.battery_filled_segments(pct), segs, pct)

    def test_segment_clamp(self):
        self.assertEqual(ft_layout.battery_filled_segments(-5), 0)
        self.assertEqual(ft_layout.battery_filled_segments(150), 5)
        self.assertEqual(ft_layout.battery_filled_segments("90"), 5)
        self.assertEqual(ft_layout.battery_filled_segments("nope"), 0)
        self.assertEqual(ft_layout.battery_filled_segments(None), 0)

    def test_parse_capacity_text(self):
        self.assertEqual(ft_layout.parse_battery_capacity_text("90\n"), 90)
        self.assertEqual(ft_layout.parse_battery_capacity_text(" 7 "), 7)
        self.assertEqual(ft_layout.parse_battery_capacity_text("100"), 100)
        self.assertEqual(ft_layout.parse_battery_capacity_text("-3"), 0)
        self.assertEqual(ft_layout.parse_battery_capacity_text("999"), 100)
        self.assertIsNone(ft_layout.parse_battery_capacity_text(""))
        self.assertIsNone(ft_layout.parse_battery_capacity_text("abc"))
        self.assertIsNone(ft_layout.parse_battery_capacity_text(None))

    def test_pick_max1720x_over_other_battery(self):
        entries = [
            ("BAT0", "Battery", True),
            ("max1720x_bat_7-36", "Battery", True),
            ("pm8550b-charger", "Unknown", False),
        ]
        path = ft_layout.pick_headset_battery_capacity_path(entries)
        self.assertEqual(path, "/sys/class/power_supply/max1720x_bat_7-36/capacity")

    def test_pick_fallback_single_battery(self):
        entries = [("some_bat", "Battery", True), ("mains", "Mains", False)]
        path = ft_layout.pick_headset_battery_capacity_path(entries)
        self.assertEqual(path, "/sys/class/power_supply/some_bat/capacity")

    def test_pick_none_when_no_battery(self):
        self.assertIsNone(ft_layout.pick_headset_battery_capacity_path([
            ("pm8550b-charger", "Unknown", False),
        ]))


class StoragePooling(unittest.TestCase):
    """Device = sum unique internal mounts; SD = mmc, including unmounted sysfs size."""

    def test_classify(self):
        self.assertEqual(ft_layout.classify_block_device("/dev/sda8"), "device")
        self.assertEqual(ft_layout.classify_block_device("/dev/mmcblk0p1"), "sd")
        self.assertIsNone(ft_layout.classify_block_device("/dev/zram0"))
        self.assertIsNone(ft_layout.classify_block_device("/dev/loop0"))
        self.assertIsNone(ft_layout.classify_block_device("tmpfs"))

    def test_normalize_subvol_source(self):
        self.assertEqual(
            ft_layout.normalize_block_source("/dev/sda8[/.steamos/offload/var/log]"),
            "/dev/sda8",
        )

    def test_frame_like_device_sum_dedupes_home_binds(self):
        # Mirror Steam Frame: /, /var, /home + many /home bind mounts, tiny /persist.
        G = 1024 ** 3
        mounts = [
            ("/dev/sda4", "/", "btrfs", 10 * G, 4 * G),
            ("/dev/sda6", "/var", "ext4", G // 4, G // 40),
            ("/dev/sda8", "/home", "ext4", 214 * G, 200 * G),
            ("/dev/sda8[/.steamos/offload/var/log]", "/var/log", "ext4", 214 * G, 200 * G),
            ("/dev/sda8[/nix]", "/nix", "ext4", 214 * G, 200 * G),
            ("/dev/sdd1", "/persist", "ext4", G // 8, G // 1000),
            ("tmpfs", "/tmp", "tmpfs", 8 * G, G),
            ("overlay", "/etc", "overlay", G // 4, G // 40),
        ]
        pools = ft_layout.sum_storage_pools(mounts)
        self.assertTrue(pools["device"]["present"])
        # Unique: sda4 + sda6 + sda8 + sdd1 (home binds collapsed)
        expected_total = 10 * G + G // 4 + 214 * G + G // 8
        expected_used = 4 * G + G // 40 + 200 * G + G // 1000
        self.assertEqual(pools["device"]["total"], expected_total)
        self.assertEqual(pools["device"]["used"], expected_used)
        self.assertFalse(pools["sd"]["present"])
        self.assertGreater(pools["device"]["pct"], 85)

    def test_mounted_sd(self):
        G = 1024 ** 3
        mounts = [
            ("/dev/sda8", "/home", "ext4", 100 * G, 40 * G),
            ("/dev/mmcblk0p1", "/run/media/deck/android", "exfat", 476 * G, 100 * G),
        ]
        pools = ft_layout.sum_storage_pools(mounts)
        self.assertTrue(pools["sd"]["present"])
        self.assertTrue(pools["sd"]["mounted"])
        self.assertEqual(pools["sd"]["total"], 476 * G)
        self.assertEqual(pools["sd"]["used"], 100 * G)
        self.assertEqual(pools["sd"]["pct"], ft_layout.storage_usage_pct(476 * G, 100 * G))

    def test_unmounted_sd_from_sysfs(self):
        G = 1024 ** 3
        mounts = [("/dev/sda8", "/home", "ext4", 100 * G, 10 * G)]
        pools = ft_layout.sum_storage_pools(mounts, sd_block_bytes={"mmcblk0": 512 * G})
        self.assertTrue(pools["sd"]["present"])
        self.assertFalse(pools["sd"]["mounted"])
        self.assertEqual(pools["sd"]["total"], 512 * G)
        self.assertEqual(pools["sd"]["used"], 0)
        self.assertEqual(pools["sd"]["pct"], 0)

    def test_usage_pct_ceil(self):
        self.assertEqual(ft_layout.storage_usage_pct(100, 1), 1)
        self.assertEqual(ft_layout.storage_usage_pct(100, 0), 0)
        self.assertEqual(ft_layout.storage_usage_pct(0, 5), 0)
        self.assertEqual(ft_layout.storage_usage_pct(100, 100), 100)


class DateInstrumentFormat(unittest.TestCase):
    def test_tue_29_sep(self):
        # 2026-09-29 was a Tuesday (wday=2 if Sun=0)
        day, dom, mon = ft_layout.format_date_instrument(2, 29, 8)
        self.assertEqual(day, "TUE")
        self.assertEqual(dom, 29)
        self.assertEqual(mon, "SEP")

    def test_sunday_january(self):
        day, dom, mon = ft_layout.format_date_instrument(0, 1, 0)
        self.assertEqual((day, dom, mon), ("SUN", 1, "JAN"))

    def test_clamp(self):
        day, dom, mon = ft_layout.format_date_instrument(99, 0, -1)
        self.assertEqual(day, "SAT")
        self.assertEqual(dom, 1)
        self.assertEqual(mon, "JAN")


if __name__ == "__main__":
    unittest.main()
