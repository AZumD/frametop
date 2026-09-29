#!/usr/bin/env python3
"""Unit tests for soft-follow dead-zone lock push (mirrors screens/vr.cpp PushFollowLock).

Run:
  python3 test/test_follow_deadzone.py
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "layout"))
import ft_layout  # noqa: E402


def wrap_pi(a):
    return math.remainder(a, 2 * math.pi)


def yaw_only(yaw, x=0.0, y=0.0, z=0.0):
    c, s = math.cos(yaw), math.sin(yaw)
    return [
        [c, 0.0, s, x],
        [0.0, 1.0, 0.0, y],
        [-s, 0.0, c, z],
    ]


def mat_yaw(m):
    return math.atan2(m[0][2], m[2][2])


def push_yaw_lock(lock, cur, zone_deg):
    """Yaw-follow push: only yaw gated; position taken from cur."""
    ly, cy = mat_yaw(lock), mat_yaw(cur)
    dy = wrap_pi(cy - ly)
    zone = math.radians(zone_deg)
    yaw = ly
    if abs(dy) > zone:
        yaw = ly + dy - math.copysign(zone, dy)
    out = yaw_only(yaw, cur[0][3], cur[1][3], cur[2][3])
    return out


def push_position_lock(lock, cur, zone_m):
    d = [cur[i][3] - lock[i][3] for i in range(3)]
    length = math.sqrt(sum(v * v for v in d))
    out = [row[:] for row in lock]
    if length > zone_m and length > 1e-9:
        f = (length - zone_m) / length
        for i in range(3):
            out[i][3] = lock[i][3] + d[i] * f
    return out


class FollowDeadzonePush(unittest.TestCase):
    def test_yaw_inside_zone_unchanged(self):
        lock = yaw_only(0.0)
        cur = yaw_only(math.radians(10))
        out = push_yaw_lock(lock, cur, zone_deg=15)
        self.assertAlmostEqual(mat_yaw(out), 0.0, places=5)

    def test_yaw_outside_pushes_excess_only(self):
        lock = yaw_only(0.0)
        cur = yaw_only(math.radians(25))
        out = push_yaw_lock(lock, cur, zone_deg=15)
        # Excess = 10° → lock moves to +10°, keeping 15° of slack to cur.
        self.assertAlmostEqual(math.degrees(mat_yaw(out)), 10.0, places=4)
        self.assertAlmostEqual(math.degrees(wrap_pi(mat_yaw(cur) - mat_yaw(out))), 15.0, places=4)

    def test_yaw_keeps_walking_position(self):
        lock = yaw_only(0.0, 0, 1.6, 0)
        cur = yaw_only(math.radians(5), 0.4, 1.6, -0.2)
        out = push_yaw_lock(lock, cur, zone_deg=15)
        self.assertAlmostEqual(out[0][3], 0.4)
        self.assertAlmostEqual(out[2][3], -0.2)

    def test_position_inside_zone(self):
        lock = yaw_only(0.0, 0, 0, 0)
        cur = yaw_only(0.0, 0.05, 0, 0)
        out = push_position_lock(lock, cur, zone_m=0.15)
        self.assertAlmostEqual(out[0][3], 0.0)

    def test_position_outside_pushes_excess(self):
        lock = yaw_only(0.0, 0, 0, 0)
        cur = yaw_only(0.0, 0.40, 0, 0)
        out = push_position_lock(lock, cur, zone_m=0.15)
        self.assertAlmostEqual(out[0][3], 0.25, places=5)

    def test_layout_helpers(self):
        off = ft_layout.screen_follow_deadzone({})
        self.assertFalse(off["enabled"])
        on = ft_layout.screen_follow_deadzone(
            {"follow_deadzone": {"enabled": True, "degrees": 20, "metres": 0.2}}
        )
        self.assertTrue(on["enabled"])
        self.assertAlmostEqual(on["degrees"], 20)
        spatial = ft_layout.spatial_screen(
            {"pos": [0, 0, -2], "face": [0, 0], "roll": 0, "metres": 2,
             "follow_deadzone": {"enabled": True, "degrees": 12}}
        )
        self.assertIn("follow_deadzone", spatial)
        self.assertTrue(spatial["follow_deadzone"]["enabled"])
        spatial_off = ft_layout.spatial_screen({"pos": [0, 0, -2], "face": [0, 0], "metres": 2})
        self.assertNotIn("follow_deadzone", spatial_off)


if __name__ == "__main__":
    unittest.main()
