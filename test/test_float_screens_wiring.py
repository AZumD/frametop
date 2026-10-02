#!/usr/bin/env python3
"""Phase 3A: floating spare-output panels wired into ft-screens (source checks).

Asserts compositor/vr carry --spares, MAX_SCREENS>=24, frametop.float.* overlays,
float/unfloat commands, and that alone/keyboard/instrument symbols still exist.

  python3 test/test_float_screens_wiring.py
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSITOR = (ROOT / "screens" / "compositor.c").read_text(encoding="utf-8", errors="replace")
VR_H = (ROOT / "screens" / "vr.h").read_text(encoding="utf-8", errors="replace")
VR_CPP = (ROOT / "screens" / "vr.cpp").read_text(encoding="utf-8", errors="replace")
HEADLESS = (ROOT / "screens" / "test" / "headless.sh").read_text(encoding="utf-8", errors="replace")


class FloatScreensWiring(unittest.TestCase):
    def test_max_screens_at_least_24(self):
        m = re.search(r"#define\s+MAX_SCREENS\s+(\d+)", COMPOSITOR)
        self.assertIsNotNone(m)
        self.assertGreaterEqual(int(m.group(1)), 24)

    def test_spares_argument(self):
        self.assertIn("--spares", COMPOSITOR)
        self.assertIn('strcmp(argv[i], "--spares")', COMPOSITOR)
        self.assertIn("s.spares", COMPOSITOR)
        self.assertIn("--spares", HEADLESS)

    def test_float_apis_in_header(self):
        self.assertIn("ft_vr_float_create", VR_H)
        self.assertIn("ft_vr_float_output", VR_H)

    def test_overlay_keys(self):
        self.assertIn("frametop.float.", VR_CPP)
        self.assertIn('frametop.float.%d.sub.%d', VR_CPP)
        self.assertIn('frametop.catcher', VR_CPP)

    def test_float_create_unfloat_commands(self):
        self.assertIn("ft_vr_float_create", VR_CPP)
        self.assertIn("ft_vr_float_output", COMPOSITOR)
        self.assertRegex(VR_CPP, r'sscanf\(cmd,\s*"float ')
        self.assertRegex(VR_CPP, r'sscanf\(cmd,\s*"unfloat ')
        self.assertIn("void SetFloat(", VR_CPP)
        self.assertIn("void Unfloat(", VR_CPP)

    def test_alone_keyboard_instrument_preserved(self):
        self.assertIn("bool alone", VR_CPP)
        self.assertIn("conceal", VR_CPP)
        self.assertIn("keyboard::EndDragBy", VR_CPP)
        self.assertIn("ft_vr_keyboard_show", VR_CPP)
        self.assertIn("Instrument", VR_CPP)
        self.assertIn("frametop.instrument.", VR_CPP)
        # alone/conceal must not wipe floats via "all"
        self.assertIn("if (!s.floating) fn(s)", VR_CPP)

    def test_pointer_ignore_frametop_protection_still_documented_in_compositor(self):
        # click handler still treats frametop.* as our panels (typing stays on desktop)
        self.assertIn('strncmp(buf + 6, "frametop.", 9)', COMPOSITOR)


if __name__ == "__main__":
    unittest.main()
