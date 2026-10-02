#!/usr/bin/env python3
"""Cross-panel drag/drop wiring: FramePanel classification + held-drag focus handoff.

Semantic source checks for the Phase 3A DnD path (screen↔float↔float). Runtime
acceptance still needs headset confirmation.

  python3 test/test_float_cross_panel_dnd.py
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def frame_panel_py(key: str) -> bool:
    """Mirror pointer FramePanel() semantics for unit checks."""
    for prefix in ("frametop.screen.", "frametop.float."):
        if not key.startswith(prefix):
            continue
        rest = key[len(prefix) :]
        dot = rest.find(".")
        return dot < 0 or rest[dot : dot + 5] == ".sub."
    return False


class FramePanelClassification(unittest.TestCase):
    def test_content_panels(self):
        self.assertTrue(frame_panel_py("frametop.screen.1"))
        self.assertTrue(frame_panel_py("frametop.float.4"))
        self.assertTrue(frame_panel_py("frametop.float.4.sub.0"))

    def test_controls_excluded(self):
        self.assertFalse(frame_panel_py("frametop.float.4.bar"))
        self.assertFalse(frame_panel_py("frametop.float.4.dock"))
        self.assertFalse(frame_panel_py("frametop.float.4.close"))
        self.assertFalse(frame_panel_py("frametop.screen.1.bar"))
        self.assertFalse(frame_panel_py("frametop.instrument.clock"))
        self.assertFalse(frame_panel_py("frametop.catcher"))

    def test_cpp_matches(self):
        p = read("pointer/helper/ft-pointer.cpp")
        self.assertIn("bool FramePanel(", p)
        self.assertIn('"frametop.screen."', p)
        self.assertIn('"frametop.float."', p)
        self.assertIn(".sub.", p)


class HeldDragRetarget(unittest.TestCase):
    def test_press_key_and_retarget(self):
        p = read("pointer/helper/ft-pointer.cpp")
        self.assertIn("pressKey", p)
        self.assertIn("if (leftHeld && !pressKey.empty())", p)
        self.assertIn("if (FramePanel(lastHit))", p)
        self.assertIn('SendTo(out, "ft_screens", "up")', p)
        # Retarget updates locked distance onto another FramePanel
        self.assertIn("dragDistance = h.along, lastHit = h.key", p)

    def test_pointer_ignore_guard_intact(self):
        p = read("pointer/helper/ft-pointer.cpp")
        self.assertIn('rfind("frametop.", 0) == 0) return false', p)


class FocusHandoff(unittest.TestCase):
    def test_leave_suppressed_while_held(self):
        vr = read("screens/vr.cpp")
        self.assertIn("case vr::VREvent_FocusLeave:", vr)
        # Both comment variants acceptable
        self.assertTrue(
            "keep KWin pointer while a button is held" in vr
            or "KWin keeps the pointer while a button is held" in vr
        )
        i = vr.find("case vr::VREvent_FocusLeave:")
        body = vr[i : i + 350]
        self.assertIn("g_press.buttons", body)
        self.assertIn("return", body)
        self.assertIn("FT_LEAVE", body)

    def test_enter_offset_so_motion_not_dropped(self):
        """wlroots drops motion to the enter position; enter must be one unit off."""
        c = read("screens/compositor.c")
        self.assertIn("wlr_seat_pointer_notify_enter(s->seat, surface, x + 1, y)", c)
        self.assertIn("wlr_seat_pointer_notify_motion(s->seat, t, x, y)", c)
        # Seat coords already mapped in vr.cpp — do not divide by scale again
        self.assertIn("ft_event x/y are already seat coords", c)
        self.assertNotRegex(
            c,
            r"const double x = e->x / s->scale\[e->screen\]",
        )

    def test_motion_updates_press_screen(self):
        vr = read("screens/vr.cpp")
        self.assertIn("if (g_press.buttons) g_press.screen = index", vr)

    def test_catcher_and_up_backstop(self):
        vr = read("screens/vr.cpp")
        self.assertIn("void UpdateCatcher(", vr)
        self.assertIn("void ReleaseAway(", vr)
        self.assertIn('strcmp(cmd, "up")', vr)
        self.assertIn("frametop.catcher", vr)

    def test_compositor_enter_on_motion_or_button(self):
        c = read("screens/compositor.c")
        # FT_MOTION and FT_BUTTON share the enter/motion path
        block = c[c.find("case FT_MOTION:") : c.find("case FT_SCROLL:")]
        self.assertIn("pointer_focus != sc", block)
        self.assertIn("x + 1", block)
        self.assertIn("FT_BUTTON", block)


class SemanticPathsDocumented(unittest.TestCase):
    def test_docs_mention_cross_panel(self):
        docs = read("docs/floating-windows.md")
        self.assertIn("Crossing panels", docs)
        self.assertIn("drag lock", docs.lower())
        floatd = read("docs/README/FT_FLOATD.md")
        self.assertIn("x+1", floatd)


if __name__ == "__main__":
    unittest.main()
