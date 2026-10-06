#!/usr/bin/env python3
"""Source contract: ShowToolbar(true) refaces every cell (invisible-icon bug).

A recycled OpenVR overlay can keep a blank texture after Hide/Show or a task
rebuild. RebuildToolbarForTasks already refaces; ShowToolbar must too so
dashboard yield cannot leave blank buttons.

Run:
  python3 test/test_toolbar_reface_on_show.py
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLBAR = (ROOT / "screens" / "desktop_toolbar.inc").read_text(encoding="utf-8", errors="replace")
VR = (ROOT / "screens" / "vr.cpp").read_text(encoding="utf-8", errors="replace")


class ToolbarRefaceOnShow(unittest.TestCase):
    def test_show_toolbar_refaces_cells(self):
        # Extract ShowToolbar body (until the next top-level void).
        m = re.search(
            r"void ShowToolbar\(bool on\) \{(.*?)\n\}",
            TOOLBAR,
            re.S,
        )
        self.assertIsNotNone(m, "ShowToolbar missing")
        body = m.group(1)
        self.assertIn("RefaceToolbarBtn", body)
        self.assertIn("ApplyToolbarAlpha(true)", body)

    def test_light_toolbar_sets_mouse_scale(self):
        m = re.search(r"void LightToolbarBtn\(ToolbarBtn &b, bool lit\) \{(.*?)\n\}", TOOLBAR, re.S)
        self.assertIsNotNone(m)
        self.assertIn("SetOverlayMouseScale", m.group(1))

    def test_make_panel_purges_slot_overlays(self):
        self.assertIn(".slot%d", VR)
        self.assertIn("DestroyOverlay(leftover)", VR)
        # MakePanel must not create digit slot chrome under screens.
        self.assertNotRegex(VR, r'chrome\("slot')
        self.assertNotIn("slotButton[", VR)

    def test_place_chrome_always_sizes_dock(self):
        m = re.search(r"void PlaceChrome\(Screen &s\) \{(.*?)\n\}", VR, re.S)
        self.assertIsNotNone(m, "PlaceChrome missing")
        body = m.group(1)
        self.assertIn("setW(s.dockButton", body)
        # Must not be gated on floating only.
        self.assertNotRegex(body, r"if \(s\.floating\).*setW\(s\.dockButton", re.S)


if __name__ == "__main__":
    unittest.main()
