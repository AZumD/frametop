#!/usr/bin/env python3
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ToolbarBlackProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cpp = (ROOT / "test/toolbar_black_probe.cpp").read_text()
        cls.sh = (ROOT / "test/_diagnose_toolbar_black.sh").read_text()

    def test_probe_reads_visual_and_texture_state(self):
        for token in (
            "GetOverlayImageData(",
            "GetOverlayAlpha(",
            "GetOverlayColor(",
            "GetOverlaySortOrder(",
            "GetOverlayTextureBounds(",
            "GetOverlayMouseScale(",
            "IsOverlayVisible(",
        ):
            self.assertIn(token, self.cpp)
        self.assertIn("frametop.toolbar.backing", self.cpp)
        self.assertIn("frametop.toolbar.m%d.c%d", self.cpp)

    def test_probe_cannot_restart_runtime(self):
        self.assertIn("pgrep -x vrserver", self.sh)
        for dangerous in ("systemctl --user restart", "pkill", "desktops.sh restart", "VRApplication_Scene"):
            self.assertNotIn(dangerous, self.sh)
        self.assertLess(
            self.cpp.index("VRApplication_Background"),
            self.cpp.index("VRApplication_Overlay"),
        )

    def test_runner_collects_existing_toolbar_diagnostics(self):
        self.assertIn('b"toolbar taskbar"', self.sh)
        self.assertIn('b"toolbar overlays"', self.sh)
        self.assertIn("/tmp/frametop-screens.log", self.sh)


if __name__ == "__main__":
    unittest.main()
