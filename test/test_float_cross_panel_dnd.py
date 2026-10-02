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
        # Soft-follow must not clear pressKey on 0.001 matrix noise (5 cm carry threshold)
        self.assertIn("0.05f * 0.05f", p)
        self.assertNotIn("0.001f) still = false", p)

    def test_catcher_uses_nearest_hit(self):
        vr = read("screens/vr.cpp")
        i = vr.find("void UpdateCatcher(")
        body = vr[i : i + 1200]
        self.assertIn("best < 1e8", body)
        self.assertIn("hit.fDistance < best", body)

    def test_compositor_clears_before_cross_enter(self):
        c = read("screens/compositor.c")
        block = c[c.find("case FT_MOTION:") : c.find("case FT_SCROLL:")]
        self.assertIn("notify_clear_focus", block)
        self.assertIn("x + 1", block)

    def test_pointer_ignore_guard_intact(self):
        p = read("pointer/helper/ft-pointer.cpp")
        self.assertIn('rfind("frametop.", 0) == 0) return false', p)


class FocusHandoff(unittest.TestCase):
    def test_leave_suppressed_while_held(self):
        vr = read("screens/vr.cpp")
        self.assertIn('DndLog("leave-suppressed"', vr)
        self.assertIn("e.type = FT_LEAVE", vr)
        # leave-suppressed only runs inside the g_press.buttons branch
        i = vr.find('DndLog("leave-suppressed"')
        self.assertGreater(i, 0)
        self.assertIn("g_press.buttons", vr[max(0, i - 120) : i + 80])

    def test_motion_updates_press_screen(self):
        vr = read("screens/vr.cpp")
        self.assertIn("g_press.screen = index, g_press.x = sx, g_press.y = sy", vr)
        self.assertIn('DndLog("retarget"', vr)

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
