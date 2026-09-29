#!/usr/bin/env python3
"""Chrome control strip layout without SteamVR keyboard button.

Mirrors screens/vr.cpp ControlOffsets: bar, curve, roll, resize, anchor, then slots.
The under-chrome "K" / ShowKeyboard path is withdrawn.

Run:
  python3 test/test_chrome_layout.py
"""
from __future__ import annotations

import unittest

SLOT_COUNT = 6


def bar_y(height_m: float, chrome: float) -> float:
    return -(height_m / 2 + chrome * 0.06 + chrome * 12 / 256)


def control_local_x(metres: float, chrome: float, grip: float, height_m: float) -> list[tuple[str, float, float]]:
    """Return (name, local_x, local_y) for each chrome control (flat screen)."""
    bar, button, gap = chrome, grip, chrome * 0.06
    by = bar_y(height_m, chrome)
    out = [
        ("bar", 0.0, by),
        ("curve", bar / 2 + gap + button / 2, by),
        ("roll", bar / 2 + gap * 2 + button * 1.5, by),
        ("resize", metres / 2 + grip / 2, -(height_m / 2 + grip / 2)),
        ("anchor", -(bar / 2 + gap + button / 2), by),
    ]
    for i in range(SLOT_COUNT):
        x = -(bar / 2 + gap * 2 + button * 1.5 + (SLOT_COUNT - 1 - i) * (button + gap))
        out.append((f"slot{i + 1}", x, by))
    return out


class ChromeLayoutNoKeyboard(unittest.TestCase):
    def test_control_count(self):
        # 5 fixed controls + 6 slots; no keyboard button.
        names = [n for n, _, _ in control_local_x(1.0, 0.3, 0.04, 0.5625)]
        self.assertEqual(len(names), 5 + SLOT_COUNT)
        self.assertNotIn("keyboard", names)

    def test_curve_and_roll_right_of_bar(self):
        items = dict((n, (x, y)) for n, x, y in control_local_x(1.0, 0.3, 0.04, 0.5625))
        self.assertGreater(items["curve"][0], 0)
        self.assertGreater(items["roll"][0], items["curve"][0])
        self.assertLess(items["anchor"][0], 0)

    def test_slots_left_of_anchor(self):
        items = dict((n, (x, y)) for n, x, y in control_local_x(1.0, 0.3, 0.04, 0.5625))
        self.assertLess(items["slot6"][0], items["anchor"][0])
        self.assertLess(items["slot1"][0], items["slot6"][0])

    def test_no_keyboard_gap_between_roll_and_resize(self):
        # Resize is a corner tab; roll is on the bar row — they share no third button between.
        names = [n for n, _, _ in control_local_x(1.2, 0.3, 0.04, 0.675)]
        self.assertEqual(names[2:4], ["roll", "resize"])


if __name__ == "__main__":
    unittest.main()
