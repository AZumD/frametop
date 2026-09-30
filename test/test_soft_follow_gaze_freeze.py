#!/usr/bin/env python3
"""Soft-follow must not freeze yaw/position under gaze (stutter/jitter regression)."""
from __future__ import annotations

import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VR = os.path.join(ROOT, "screens", "vr.cpp")


def _fn_body(src: str, name: str) -> str:
    m = re.search(rf"void {name}\([^)]*\) \{{", src)
    if not m:
        raise AssertionError(f"missing {name}")
    start = m.end()
    depth = 1
    i = start
    while i < len(src) and depth:
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
        i += 1
    return src[start:i]


class SoftFollowGazeFreeze(unittest.TestCase):
    def test_update_follow_freezes_only_head_soft(self):
        with open(VR, encoding="utf-8", errors="replace") as f:
            src = f.read()
        body = _fn_body(src, "UpdateFollow")
        self.assertIn("attentionFocused && s.anchor == AnchorMode::HeadSoft", body)
        # Must not freeze every soft mode on focus alone.
        self.assertNotRegex(
            body,
            r"attentionFocused\)\s*\{\s*\n\s*if \(s\.followDeadzone\)",
        )
        self.assertIn("posFloorM", body)
        self.assertIn("AnchorMode::PositionFollow", body)

    def test_instrument_follow_matches(self):
        with open(VR, encoding="utf-8", errors="replace") as f:
            src = f.read()
        body = _fn_body(src, "UpdateInstrumentFollow")
        self.assertIn("attentionFocused &&", body)
        self.assertIn("inst.anchor == AnchorMode::HeadSoft", body)
        self.assertIn("posFloorM", body)
        self.assertIn("AnchorMode::PositionFollow", body)


if __name__ == "__main__":
    unittest.main()
