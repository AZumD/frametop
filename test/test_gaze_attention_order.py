#!/usr/bin/env python3
"""Tests for gaze attention opacity ordering and dashboard overlay yield."""
from __future__ import annotations

import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys_path_layout = os.path.join(ROOT, "layout")
import sys

sys.path.insert(0, sys_path_layout)
import ft_layout  # noqa: E402


class OpacityOrdering(unittest.TestCase):
    def test_swapped_active_idle_are_corrected(self):
        active, idle = ft_layout.screen_opacities({
            "active_opacity": 0.1,
            "idle_opacity": 0.9,
        })
        self.assertGreaterEqual(active, idle)
        self.assertAlmostEqual(active, 0.9)
        self.assertAlmostEqual(idle, 0.1)

    def test_normal_order_preserved(self):
        active, idle = ft_layout.screen_opacities({
            "active_opacity": 1.0,
            "idle_opacity": 0.4,
        })
        self.assertAlmostEqual(active, 1.0)
        self.assertAlmostEqual(idle, 0.4)

    def test_instrument_normalize_swaps(self):
        out = ft_layout.normalize_instrument({
            "type": "clock",
            "enabled": True,
            "active_opacity": 0.2,
            "idle_opacity": 0.8,
        })
        self.assertGreaterEqual(out["active_opacity"], out["idle_opacity"])
        self.assertAlmostEqual(out["active_opacity"], 0.8)
        self.assertAlmostEqual(out["idle_opacity"], 0.2)

    def test_vr_dashboard_yield_and_sort(self):
        path = os.path.join(ROOT, "screens", "vr.cpp")
        with open(path, encoding="utf-8", errors="replace") as f:
            src = f.read()
        self.assertIn("DashboardYieldActive()", src)
        self.assertIn("ScreenKeepsThroughDashboard", src)
        # Gaze freezes only head-soft follow (yaw/position keep moving while watched).
        self.assertIn("s.anchor == AnchorMode::HeadSoft", src)
        self.assertIn("inst.anchor == AnchorMode::HeadSoft", src)
        self.assertIn("PositionFollow", src)
        self.assertIn("posFloorM", src)
        self.assertIn("if (s.idleOpacity > s.activeOpacity) std::swap", src)
        self.assertIn("if (inst.idleOpacity > inst.activeOpacity) std::swap", src)
        # Chrome must not use elevated sort 10 (paints over Steam UI).
        self.assertNotIn("SetOverlaySortOrder(o, 10)", src)
        self.assertIn("SetOverlaySortOrder(o, 1)", src)
        # Must not force active opacity for the whole dashboard session.
        self.assertNotIn("dashboard / streaming UI open", src)


if __name__ == "__main__":
    unittest.main()
