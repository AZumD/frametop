#!/usr/bin/env python3
"""Smoke: Backend exposes Launcher QML API; Add Launcher is at the top of Spatial Instruments."""
from __future__ import annotations

import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "display-settings"))
sys.path.insert(0, os.path.join(ROOT, "layout"))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ft_display_settings import Backend  # noqa: E402
import ft_layout  # noqa: E402

QML = os.path.join(ROOT, "display-settings", "main.qml")


class AddLauncherUi(unittest.TestCase):
    def test_add_buttons_before_clock_section(self):
        with open(QML, encoding="utf-8") as f:
            qml = f.read()
        add_img = qml.index('text: "Add Image"')
        add_ln = qml.index('text: "Add Launcher"')
        clock = qml.index('text: "Clock"')
        self.assertLess(add_img, clock, "Add Image must appear above Clock")
        self.assertLess(add_ln, clock, "Add Launcher must appear above Clock")
        self.assertLess(abs(add_img - add_ln), 400, "Add Image and Add Launcher should be adjacent")
        self.assertIn("onClicked: backend.addLauncherInstrument()", qml)
        self.assertIn("onClicked: backend.addImageInstrument()", qml)

    def test_backend_api(self):
        self.assertIn("launcher", ft_layout.KNOWN_INSTRUMENT_TYPES)
        b = Backend()
        self.assertTrue(callable(b.addLauncherInstrument))
        apps = b.installedApps
        self.assertIsInstance(apps, list)
        launchers = b.launcherInstruments
        self.assertIsInstance(launchers, list)
        actions = b.semanticActions
        self.assertIsInstance(actions, list)
        self.assertTrue(actions)
        glyphs = b.launcherGlyphs
        self.assertIn("star", glyphs)


def main():
    assert "launcher" in ft_layout.KNOWN_INSTRUMENT_TYPES
    b = Backend()
    assert callable(b.addLauncherInstrument)
    apps = b.installedApps
    assert isinstance(apps, list)
    launchers = b.launcherInstruments
    assert isinstance(launchers, list)
    actions = b.semanticActions
    assert isinstance(actions, list) and actions
    glyphs = b.launcherGlyphs
    assert "star" in glyphs
    with open(QML, encoding="utf-8") as f:
        qml = f.read()
    assert 'text: "Add Launcher"' in qml
    assert qml.index('text: "Add Launcher"') < qml.index('text: "Clock"')
    print(
        "ok",
        f"apps={len(apps)} launchers={len(launchers)} actions={len(actions)} glyphs={len(glyphs)}",
    )
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("-v", "--unittest"):
        unittest.main(argv=[sys.argv[0]] + sys.argv[2:])
    raise SystemExit(main())
