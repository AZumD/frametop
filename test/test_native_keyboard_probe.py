#!/usr/bin/env python3
"""Static guard for the native SteamVR keyboard probe."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NativeKeyboardProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cpp = (ROOT / "test/native_keyboard_probe.cpp").read_text()
        cls.sh = (ROOT / "test/_probe_native_keyboard.sh").read_text()

    def test_uses_public_keyboard_api(self):
        self.assertIn("ShowKeyboardForOverlay(", self.cpp)
        self.assertIn("KeyboardFlag_Minimal", self.cpp)
        self.assertIn("KeyboardFlag_ShowArrowKeys", self.cpp)
        self.assertIn("VREvent_KeyboardCharInput", self.cpp)
        self.assertIn("GetKeyboardText(", self.cpp)
        self.assertIn("HideKeyboard()", self.cpp)

    def test_safe_openvr_init_and_live_guard(self):
        self.assertLess(
            self.cpp.index("VRApplication_Background"),
            self.cpp.index("VRApplication_Overlay"),
        )
        self.assertIn("pgrep -x vrserver", self.sh)
        self.assertNotIn("systemctl --user restart", self.sh)
        self.assertNotIn("pkill", self.sh)

    def test_program_name_fits_pgrep_limit(self):
        self.assertIn("ft-kbprobe", self.sh)
        self.assertLessEqual(len("ft-kbprobe"), 15)


if __name__ == "__main__":
    unittest.main()
