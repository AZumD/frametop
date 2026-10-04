#!/usr/bin/env python3
"""Assert the abandoned MAGIC gaze-pointer experiment is gone.

Keeps eye-gaze attention (ft-screens / Display Settings) intact — this only
checks that the old desktop pointer-follows-eyes stack and its plumbing are
absent.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Identifiers that belonged only to the deleted gaze-pointer service / helper mode.
FORBIDDEN = [
    "POINTER_GAZE",
    "POINTER_GAZE_RETAKE",
    "POINTER_GAZE_NUDGE_MAX",
    "POINTER_GAZE_HOLD",
    "POINTER_GAZE_SHOW",
    "ft_gazed",
    "ft-gazed",
    "ft-gazectl",
    "ft-gaze.cpp",
    "ft-gazeprobe",
    "gaze_toggle",
    "gazeawake",
    "frametop-gaze.service",
    "GAZE_PROBE",
    "GAZE_SETTINGS",
    "activateCurrentGazeTarget",
    "beginGazeDrag",
    "updateGazeDrag",
    "endGazeDrag",
]

# Paths that must not exist after cleanup.
GONE_PATHS = [
    "gaze",
    "gaze/ft-gaze.cpp",
    "gaze/ft-gazed",
    "gaze/ft-gazectl",
    "gaze/frametop-gaze.service",
    "gaze/README.md",
]

# Production sources that must not reintroduce the experiment.
SCAN_GLOBS = [
    "pointer/helper/ft-pointer.cpp",
    "input/input-relay.py",
    "input-settings/ft_input_settings.py",
    "input-settings/main.qml",
    "session/frametop.conf.example",
    "layout/ft_layout.py",
    "screens/vr.cpp",
    "docs/design.md",
    "docs/reference.md",
    "docs/gestures-profiles.md",
    "docs/README/OVERVIEW.md",
    "docs/README/INPUT-RELAY.md",
    "README.md",
]


class GazePointerRemoved(unittest.TestCase):
    def test_gaze_directory_gone(self):
        for rel in GONE_PATHS:
            self.assertFalse((ROOT / rel).exists(), f"still present: {rel}")

    def test_forbidden_identifiers_absent(self):
        # Uninstall helpers may still mention frametop-gaze.service for leftover cleanup.
        allow_uninstall = {"frametop-gaze.service", "ft-gazeprobe"}
        for rel in SCAN_GLOBS:
            path = ROOT / rel
            self.assertTrue(path.is_file(), f"missing scan target {rel}")
            text = path.read_text(encoding="utf-8", errors="replace")
            for token in FORBIDDEN:
                if token in allow_uninstall:
                    continue
                self.assertNotIn(token, text, f"{rel} still contains {token}")

    def test_attention_gaze_still_present(self):
        """Regression guard: screens attention path must remain."""
        vr = (ROOT / "screens/vr.cpp").read_text(encoding="utf-8", errors="replace")
        for needle in (
            "GazeTarget",
            "GazeKind",
            "attentionEnabled",
            "gazeHover",
            "SampleEyeGaze",
            'gaze state',
        ):
            self.assertIn(needle, vr, f"attention path missing {needle}")
        readme = (ROOT / "README.md").read_text(encoding="utf-8", errors="replace")
        self.assertIn(
            "Steam Frame eye-gaze attention with configurable opacity transitions",
            readme,
        )

    def test_input_actions_drop_gaze_toggle(self):
        relay = (ROOT / "input/input-relay.py").read_text(encoding="utf-8")
        m = re.search(r"ACTIONS = \((.*?)\)", relay, re.S)
        self.assertIsNotNone(m)
        self.assertNotIn("gaze_toggle", m.group(1))
        self.assertIn("follow_toggle", m.group(1))

    def test_conf_example_drops_pointer_gaze(self):
        conf = (ROOT / "session/frametop.conf.example").read_text(encoding="utf-8")
        self.assertNotRegex(conf, r"(?m)^POINTER_GAZE")
        self.assertIn("POINTER_FOLLOW=", conf)

    def test_input_settings_has_no_gaze_page(self):
        qml = (ROOT / "input-settings/main.qml").read_text(encoding="utf-8")
        self.assertNotIn("gazePage", qml)
        self.assertNotIn('text: "Gaze"', qml)
        py = (ROOT / "input-settings/ft_input_settings.py").read_text(encoding="utf-8")
        self.assertNotIn("setGazeMode", py)
        self.assertNotIn("gazeChanged", py)


if __name__ == "__main__":
    r = unittest.main(verbosity=2, exit=False).result
    sys.exit(0 if r.wasSuccessful() else 1)
