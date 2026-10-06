#!/usr/bin/env python3
"""Overlay budget + SteamVR game hide: float chrome is lazy; flatscreen games count.

Headless source checks (no SteamVR). Run:

  python3 test/test_overlay_budget_and_games.py
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


class LazyFloatChrome(unittest.TestCase):
    def test_make_panel_skips_float_chrome(self):
        vr = read("screens/vr.cpp")
        make = vr[vr.index("bool MakePanel(") : vr.index("void ft_vr_screen_create(")]
        self.assertIn("Floating spares: only the main panel", make)
        self.assertIn("if (s.floating)", make)
        # Float path returns before bar/dock/close; toolbar dock chrome is for real screens only.
        float_branch = make[make.index("if (s.floating)") : make.index("static const auto corner")]
        self.assertIn("return true;", float_branch)
        self.assertNotIn("CloseTexture", make)
        self.assertIn("DockTexture", make)  # screen "dock to toolbar" button
        self.assertIn("EnsureFloatChrome", vr)
        self.assertIn("ReleaseFloatChrome", vr)

    def test_float_lifecycle_creates_and_releases_chrome(self):
        vr = read("screens/vr.cpp")
        setf = vr[vr.index("void SetFloat(") : vr.index("void Unfloat(")]
        unf = vr[vr.index("void Unfloat(") : vr.index("void SetSub(")]
        self.assertIn("EnsureFloatChrome(s)", setf)
        self.assertIn("ReleaseFloatChrome(s)", unf)
        create = vr[vr.index("void ft_vr_float_create(") : vr.index("void ft_vr_float_output(")]
        self.assertIn("s.floatSlot = slot", create)

    def test_keepalive_skips_idle_floats_and_games(self):
        vr = read("screens/vr.cpp")
        vis = vr[vr.index("void UpdateVisibility()") : vr.index("void UpdateLasers()")]
        self.assertIn("(!s.floating || s.floatOn)", vis)
        self.assertRegex(vis, r"!visible && shared && s\.shown && !s\.alone")


class SteamVrGameDetection(unittest.TestCase):
    def test_app_activity_owns_hide_and_lasers(self):
        vr = read("screens/vr.cpp")
        self.assertIn("FlatscreenDesktopgame(", vr)
        self.assertIn("IsOverlayVisible(h)", vr)
        self.assertIn("valve.steam.desktopgame.%d", vr)
        self.assertIn("DecideAppActivity(", vr)
        update = vr[vr.index("void UpdateGame()") : vr.index("bool ModeVisible()")]
        self.assertIn("GetCurrentSceneProcessId()", update)
        self.assertIn("app_activity %s", update)
        lasers = vr[vr.index("void UpdateLasers()") : vr.index("void UpdateControls()")]
        self.assertIn("AppBlocksOutsideGamesLasers", lasers)
        self.assertNotIn("g_sceneApp", lasers)

    def test_docs_mention_flatscreen(self):
        ref = read("docs/reference.md")
        self.assertRegex(ref, re.compile(r"desktopgame|flatscreen|AppActivity", re.I))
        floatd = read("docs/README/FT_FLOATD.md")
        self.assertIn("EnsureFloatChrome", floatd)
        screens = read("docs/README/SCREENS_VR.md")
        self.assertIn("app_activity.h", screens)


if __name__ == "__main__":
    unittest.main()
