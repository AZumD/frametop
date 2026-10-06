#!/usr/bin/env python3
"""AppActivity ownership: flatscreen/gamepad presentation vs leftover desktopgame keys.

Mirrors screens/app_activity.h in pure Python (WSL may lack g++) and source-guards
vr.cpp wiring. Optionally compiles test/app_activity_harness.cpp when g++ exists.

  python3 test/test_app_activity.py
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DESKTOP, VR_SCENE, FLAT_GAME = 0, 1, 2
K_CLEAR = 2


def decide(scene, flat_vis, flat_reg, dash, st):
    """Python twin of frametop::DecideAppActivity."""
    if scene:
        if not flat_reg:
            st["latch"] = False
            st["ticks"] = 0
        return VR_SCENE
    if flat_vis:
        st["latch"] = True
        st["ticks"] = 0
        return FLAT_GAME
    if not flat_reg:
        st["latch"] = False
        st["ticks"] = 0
        return DESKTOP
    if st["latch"] and not dash:
        st["ticks"] = 0
        return FLAT_GAME
    if dash:
        st["ticks"] += 1
        if st["ticks"] >= K_CLEAR:
            st["latch"] = False
            st["ticks"] = 0
    else:
        st["ticks"] = 0
    return FLAT_GAME if st["latch"] else DESKTOP


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


class AppActivityLogic(unittest.TestCase):
    def test_matrix(self):
        st = {"latch": False, "ticks": 0}
        self.assertEqual(decide(False, False, False, False, st), DESKTOP)
        self.assertFalse(st["latch"])

        self.assertEqual(decide(True, False, False, False, st), VR_SCENE)

        st = {"latch": False, "ticks": 0}
        self.assertEqual(decide(False, True, True, True, st), FLAT_GAME)
        self.assertTrue(st["latch"])

        self.assertEqual(decide(False, False, True, False, st), FLAT_GAME)
        self.assertTrue(st["latch"])

        leftover = {"latch": False, "ticks": 0}
        self.assertEqual(decide(False, False, True, False, leftover), DESKTOP)

        st = {"latch": True, "ticks": 0}
        for _ in range(K_CLEAR):
            decide(False, False, True, True, st)
        self.assertEqual(decide(False, False, True, True, st), DESKTOP)
        self.assertFalse(st["latch"])

        st = {"latch": True, "ticks": 0}
        self.assertEqual(decide(False, False, True, True, st), FLAT_GAME)
        self.assertTrue(st["latch"])

    def test_header_constants(self):
        h = read("screens/app_activity.h")
        self.assertIn("kFlatLatchClearSamples = 6", h)
        self.assertIn("FlatGamePresentation", h)
        self.assertIn("AppBlocksOutsideGamesLasers", h)
        self.assertIn("dashboardVisible", h)
        self.assertIn("IsDesktopgameOverlayKey", h)
        self.assertIn("valve.steam.desktopgame", h)

    def test_harness_when_gxx_available(self):
        if not shutil.which("g++"):
            self.skipTest("g++ not installed")
        src = ROOT / "test" / "app_activity_harness.cpp"
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "app_activity_harness"
            r = subprocess.run(
                ["g++", "-std=c++17", f"-I{ROOT}", "-o", str(out), str(src)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 0, r.stderr or r.stdout)
            run = subprocess.run([str(out)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("ok app_activity", run.stdout)

    def test_vr_uses_decide_and_blocks_lasers(self):
        vr = read("screens/vr.cpp")
        self.assertIn('#include "app_activity.h"', vr)
        self.assertIn("DecideAppActivity(", vr)
        self.assertIn("AppBlocksOutsideGamesLasers(", vr)
        self.assertIn("AppHidesDisplays(", vr)
        self.assertIn("app_activity %s", vr)
        self.assertIn("VREvent_OverlayCreated", vr)
        self.assertIn("VREvent_OverlayDestroyed", vr)
        self.assertIn("GetOverlayKey(", vr)
        self.assertIn("SeedDesktopgameOverlays()", vr)
        update = vr[vr.index("void UpdateGame()") : vr.index("bool ModeVisible()")]
        self.assertIn("FlatscreenDesktopgame(", update)
        self.assertIn("IsDashboardVisible()", update)
        lasers = vr[vr.index("void UpdateLasers()") : vr.index("void UpdateControls()")]
        self.assertIn("AppBlocksOutsideGamesLasers", lasers)
        self.assertNotIn("g_sceneApp", lasers)

    def test_docs(self):
        self.assertIn("app_activity.h", read("docs/README/SCREENS_VR.md"))
        self.assertIn("app_activity.h", read("docs/reference.md"))
        self.assertIn("FlatGamePresentation", read("docs/README/APP_ACTIVITY.md"))


if __name__ == "__main__":
    unittest.main()
