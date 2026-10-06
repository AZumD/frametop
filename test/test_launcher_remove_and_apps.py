#!/usr/bin/env python3
"""Launcher remove + app availability: in-process layout write, host_command quoting, QML."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "display-settings"))
sys.path.insert(0, str(ROOT / "layout"))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ft_layout  # noqa: E402
from ft_display_settings import Backend, host_command  # noqa: E402

QML = ROOT / "display-settings" / "main.qml"


def _launcher(iid, desktop_id=""):
    return {
        "id": iid,
        "type": "launcher",
        "enabled": True,
        "action_kind": "application",
        "desktop_id": desktop_id,
        "metres": 0.28,
        "active_opacity": 1.0,
        "idle_opacity": 0.55,
    }


class HostCommandQuote(unittest.TestCase):
    def test_spaces_quoted_via_sh_c(self):
        with mock.patch("ft_display_settings.shutil.which", return_value="/usr/bin/distrobox-host-exec"):
            real_getuid = getattr(os, "getuid", None)
            if real_getuid is None:
                os.getuid = lambda: 1000  # type: ignore[attr-defined]
            try:
                with mock.patch("os.getuid", return_value=1000):
                    argv = host_command(
                        "/tmp/ft-layout",
                        "instrument",
                        "desktop",
                        "launcher",
                        "Beat Saber.desktop",
                    )
            finally:
                if real_getuid is None and hasattr(os, "getuid"):
                    delattr(os, "getuid")
        self.assertEqual(argv[0], "env")
        self.assertIn("distrobox-host-exec", argv)
        self.assertIn("sh", argv)
        self.assertIn("-c", argv)
        script = argv[argv.index("-c") + 1]
        self.assertIn("Beat Saber.desktop", script)
        self.assertIn("'Beat Saber.desktop'", script)


class InProcessLauncherMutations(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.layout_path = Path(self.tmp.name) / "layout.json"
        self.patcher = mock.patch.object(ft_layout, "LAYOUT_PATH", str(self.layout_path))
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        ft_layout.save_layout({
            "screens": [],
            "instruments": [
                _launcher("launcher", "gone.desktop"),
                _launcher("launcher-2", ""),
            ],
        })
        self.backend = Backend()
        self.backend._run = mock.Mock()  # type: ignore[method-assign]
        self.backend._proc = None

    def test_remove_drops_from_layout_and_calls_host(self):
        self.backend.removeLauncherInstrument("launcher-2")
        ids = [i["id"] for i in ft_layout.instruments_from_layout(ft_layout.load_layout())]
        self.assertEqual(ids, ["launcher"])
        self.backend._run.assert_called_once()
        args = self.backend._run.call_args[0]
        self.assertEqual(args[0], "Removing Launcher")
        self.assertEqual(args[1:], ("instrument", "remove", "launcher-2"))

    def test_remove_when_host_busy_still_saves(self):
        self.backend._proc = object()
        self.backend.removeLauncherInstrument("launcher")
        ids = [i["id"] for i in ft_layout.instruments_from_layout(ft_layout.load_layout())]
        self.assertEqual(ids, ["launcher-2"])
        self.backend._run.assert_not_called()

    def test_set_desktop_writes_layout_immediately(self):
        self.backend.setLauncherDesktop("launcher", "org.kde.dolphin.desktop")
        inst = ft_layout.instrument_entry(ft_layout.load_layout(), "launcher")
        self.assertEqual(inst["desktop_id"], "org.kde.dolphin.desktop")
        self.assertEqual(inst["action_kind"], "application")
        self.backend._run.assert_called_once()
        args = self.backend._run.call_args[0]
        self.assertEqual(args[-1], "org.kde.dolphin.desktop")

    def test_is_app_in_chooser_empty_true(self):
        self.assertTrue(self.backend.isAppInChooser(""))
        self.assertTrue(self.backend.isAppInChooser(None))


class DesktopCliSpaces(unittest.TestCase):
    def test_desktop_joins_remaining_args(self):
        src = (ROOT / "layout" / "ft_layout.py").read_text(encoding="utf-8")
        self.assertIn('desk = " ".join(args[1:]).strip()', src)


class QmlContracts(unittest.TestCase):
    def test_remove_pops_immediately(self):
        qml = QML.read_text(encoding="utf-8")
        self.assertIn("backend.removeLauncherInstrument(id)", qml)
        self.assertIn("root.pageStack.pop()", qml)
        self.assertNotIn("_pendingRemoveId", qml)
        self.assertIn("backend.isAppInChooser(ln.desktopId)", qml)


if __name__ == "__main__":
    unittest.main()
