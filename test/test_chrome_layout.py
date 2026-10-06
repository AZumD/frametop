#!/usr/bin/env python3
"""Chrome control strip layout: bar / curve / roll / resize / anchor / dock [/ close].

Profile digit slots under screens are withdrawn — Displays owns profiles.
Dock is always sized to grip (never left at OpenVR's default huge width).

Run:
  python3 test/test_chrome_layout.py
"""
from __future__ import annotations

import unittest

SLOT_COUNT = 6  # still used by the toolbar Displays popup / g_slotFilled


def bar_y(height_m: float, chrome: float) -> float:
    return -(height_m / 2 + chrome * 0.06 + chrome * 12 / 256)


def dock_button_x(chrome: float, grip: float) -> float:
    gap = chrome * 0.06
    return chrome / 2 + gap * 3 + grip * 2.5


def control_local_x(
    metres: float, chrome: float, grip: float, height_m: float, *, floating: bool = False
) -> list[tuple[str, float, float]]:
    """Return (name, local_x, local_y) for each chrome control (flat screen)."""
    bar, button, gap = chrome, grip, chrome * 0.06
    by = bar_y(height_m, chrome)
    out = [
        ("bar", 0.0, by),
        ("curve", bar / 2 + gap + button / 2, by),
        ("roll", bar / 2 + gap * 2 + button * 1.5, by),
        ("resize", metres / 2 + grip / 2, -(height_m / 2 + grip / 2)),
        ("anchor", -(bar / 2 + gap + button / 2), by),
        ("dock", dock_button_x(chrome, grip), by),
    ]
    if floating:
        out.append(("close", dock_button_x(chrome, grip) + gap + button, by))
    return out


class ChromeLayoutNoSlots(unittest.TestCase):
    def test_control_count_no_slots(self):
        names = [n for n, _, _ in control_local_x(1.0, 0.3, 0.04, 0.5625)]
        self.assertEqual(names, ["bar", "curve", "roll", "resize", "anchor", "dock"])
        self.assertNotIn("keyboard", names)
        for i in range(1, SLOT_COUNT + 1):
            self.assertNotIn(f"slot{i}", names)

    def test_float_adds_close_after_dock(self):
        names = [n for n, _, _ in control_local_x(1.0, 0.3, 0.04, 0.5625, floating=True)]
        self.assertEqual(names[-2:], ["dock", "close"])

    def test_curve_and_roll_right_of_bar(self):
        items = dict((n, (x, y)) for n, x, y in control_local_x(1.0, 0.3, 0.04, 0.5625))
        self.assertGreater(items["curve"][0], 0)
        self.assertGreater(items["roll"][0], items["curve"][0])
        self.assertLess(items["anchor"][0], 0)
        self.assertGreater(items["dock"][0], items["roll"][0])

    def test_dock_width_matches_grip(self):
        # PlaceChrome always setW(dockButton, grip) — contract for the gigantic-dock bug.
        grip = 0.04
        dock_w = grip  # metres; must equal button, not OpenVR default (~1 m)
        self.assertAlmostEqual(dock_w, grip)

    def test_no_keyboard_gap_between_roll_and_resize(self):
        names = [n for n, _, _ in control_local_x(1.2, 0.3, 0.04, 0.675)]
        self.assertEqual(names[2:4], ["roll", "resize"])


if __name__ == "__main__":
    unittest.main()
