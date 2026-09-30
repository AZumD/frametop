#!/usr/bin/env python3
"""Display Settings exposes a Background tab wired to scripts/frame-background."""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "display-settings"))
sys.path.insert(0, os.path.join(ROOT, "layout"))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ft_display_settings import BACKGROUND_PRESETS, Backend, FRAME_BACKGROUND  # noqa: E402

QML = os.path.join(ROOT, "display-settings", "main.qml")


class BackgroundTabUi(unittest.TestCase):
    def test_qml_has_background_tab(self):
        with open(QML, encoding="utf-8") as f:
            qml = f.read()
        self.assertIn('{ text: "Background", icon: "wallpaper", page: backgroundPage }', qml)
        self.assertIn("id: backgroundPage", qml)
        self.assertIn("backend.setBackgroundPreset", qml)
        self.assertIn("backend.pickBackgroundFile", qml)
        self.assertIn("backend.refreshBackground", qml)
        self.assertIn("backend.openBackgroundDirectory", qml)
        self.assertIn("Open backgrounds folder", qml)
        self.assertIn("openBackgroundPicker", qml)
        self.assertIn("pickBackgroundFile", qml)
        self.assertIn('background: backgroundPage', qml)

    def test_backend_api_and_presets(self):
        self.assertTrue(os.path.isfile(FRAME_BACKGROUND))
        ids = [p["id"] for p in BACKGROUND_PRESETS]
        self.assertEqual(ids, ["aurora", "night_mountains", "aurorasky"])
        b = Backend()
        self.assertTrue(callable(b.refreshBackground))
        self.assertTrue(callable(b.setBackgroundPreset))
        self.assertTrue(callable(b.setBackgroundFile))
        self.assertTrue(callable(b.openBackgroundDirectory))
        self.assertTrue(callable(b.ensureBackgroundDirectory))
        self.assertTrue(callable(b.pickBackgroundFile))
        self.assertTrue(b.backgroundDirectory.endswith("frametop-backgrounds"))
        self.assertIsInstance(b.backgroundPresets, list)
        self.assertEqual(len(b.backgroundPresets), 3)

    def test_pick_background_file_starts_in_background_dir(self):
        from ft_display_settings import BACKGROUND_DIR

        b = Backend()
        calls = []
        b.setBackgroundFile = lambda path: calls.append(path)  # type: ignore
        with mock.patch("ft_display_settings.QFileDialog.getOpenFileName",
                        return_value=("/tmp/x.png", "")) as dlg:
            b.pickBackgroundFile()
        self.assertTrue(os.path.isdir(BACKGROUND_DIR))
        dlg.assert_called_once()
        args, kwargs = dlg.call_args
        # getOpenFileName(parent, title, dir, filter)
        self.assertEqual(args[2], BACKGROUND_DIR)
        self.assertIn("*.hdr", args[3])
        self.assertEqual(calls, ["/tmp/x.png"])

    def test_apply_background_status(self):
        b = Backend()
        b._apply_background_status(
            {
                "mode": "image",
                "preset": "night_mountains",
                "background": "/opt/steamvr/resources/backgrounds/night_mountains.png",
                "exists": True,
                "width": 8192,
                "height": 4096,
            }
        )
        self.assertEqual(b.backgroundMode, "image")
        self.assertEqual(b.backgroundPreset, "night_mountains")
        self.assertEqual(b.backgroundFileName, "night_mountains.png")
        self.assertTrue(b.backgroundExists)
        self.assertIn("8192", b.backgroundSizeText)
        self.assertIn("2:1", b.backgroundSizeText)

    def test_set_background_preset_argv(self):
        b = Backend()
        calls = []

        def capture(label, *args):
            calls.append((label, args))

        b._run_background = capture  # type: ignore[method-assign]
        b.setBackgroundPreset("aurora")
        b.setBackgroundPreset("night_mountains")
        b.setBackgroundPreset("aurorasky")
        self.assertEqual(
            calls,
            [
                ("Background Aurora", ("aurora",)),
                ("Background image", ("set", "night_mountains")),
                ("Background image", ("set", "aurorasky")),
            ],
        )

    def test_set_background_file_resolves_and_runs(self):
        b = Backend()
        calls = []
        b._run_background = lambda label, *args: calls.append((label, args))  # type: ignore
        with mock.patch(
            "ft_display_settings.resolve_image_source_path",
            return_value="/tmp/fake-equirect.png",
        ):
            b.setBackgroundFile("file:///tmp/fake-equirect.png")
        self.assertEqual(calls, [("Background image", ("set", "/tmp/fake-equirect.png"))])


    def test_open_background_directory(self):
        from ft_display_settings import BACKGROUND_DIR

        b = Backend()
        with mock.patch("ft_display_settings.QDesktopServices.openUrl", return_value=True) as open_url:
            b.openBackgroundDirectory()
        self.assertTrue(os.path.isdir(BACKGROUND_DIR))
        open_url.assert_called_once()
        url = open_url.call_args[0][0]
        self.assertTrue(url.isLocalFile())
        self.assertEqual(os.path.normpath(url.toLocalFile()), os.path.normpath(BACKGROUND_DIR))


if __name__ == "__main__":
    raise SystemExit(unittest.main(verbosity=2))
