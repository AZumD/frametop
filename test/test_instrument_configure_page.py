#!/usr/bin/env python3
"""Configure must open a pushed ScrollablePage (not an empty Kirigami.Dialog).

Run:
  python3 test/test_instrument_configure_page.py
"""

from __future__ import annotations

import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QML = os.path.join(ROOT, "display-settings", "main.qml")


class InstrumentConfigurePage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(QML, encoding="utf-8") as f:
            cls.qml = f.read()

    def test_uses_pushed_page_not_dialog(self):
        self.assertIn("id: instrumentEditPage", self.qml)
        self.assertIn('objectName: "instrumentEditPage"', self.qml)
        self.assertIn("pageStack.push(instrumentEditPage)", self.qml)
        self.assertNotIn("id: editSheet", self.qml)
        self.assertNotIn("settings dialog (one shared)", self.qml)

    def test_builtin_form_visible_guard(self):
        self.assertIn(
            'visible: ["clock", "date", "battery", "media", "storage", "sd"].indexOf(epage.editKind) >= 0',
            self.qml,
        )
        self.assertIn('Kirigami.FormData.label: "Anchor:"', self.qml)
        self.assertIn('Kirigami.FormData.label: "Size (metres):"', self.qml)

    def test_open_helpers_push_page(self):
        self.assertIn("function openBuiltin(key)", self.qml)
        self.assertIn("root.instrumentEditKey = key", self.qml)
        for key in ("clock", "date", "battery", "media", "storage", "sd"):
            self.assertIn(f'onClicked: ipage.openBuiltin("{key}")', self.qml)

    def test_no_actions_property_clash(self):
        # Custom `property var actions` collided with Kirigami.Page.actions and
        # prevented the whole app from loading ("Property value set multiple times").
        self.assertIn("property var semanticActions: backend.semanticActions", self.qml)
        self.assertNotIn("property var actions: backend.semanticActions", self.qml)
        self.assertIn("model: epage.semanticActions", self.qml)

    def test_root_edit_state(self):
        self.assertIn("property string instrumentEditKey:", self.qml)
        self.assertIn("property var instrumentEditImage:", self.qml)
        self.assertIn("property var instrumentEditLauncher:", self.qml)


if __name__ == "__main__":
    unittest.main()
