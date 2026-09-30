#!/usr/bin/env python3
"""remove_instrument must drop launcher ids including bare 'launcher'."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "layout"))
import ft_layout  # noqa: E402


class RemoveLauncher(unittest.TestCase):
    def test_remove_bare_launcher(self):
        layout = {
            "instruments": [
                {"id": "clock", "type": "clock", "enabled": True},
                {"id": "launcher", "type": "launcher", "enabled": True,
                 "action_kind": "application", "desktop_id": "x.desktop"},
            ]
        }
        out = ft_layout.remove_instrument(layout, "launcher")
        ids = [i["id"] for i in ft_layout.instruments_from_layout(out)]
        self.assertNotIn("launcher", ids)
        self.assertIn("clock", ids)

    def test_remove_launcher_n(self):
        layout = {
            "instruments": [
                {"id": "launcher", "type": "launcher", "enabled": True},
                {"id": "launcher-2", "type": "launcher", "enabled": True},
            ]
        }
        out = ft_layout.remove_instrument(layout, "launcher-2")
        ids = [i["id"] for i in ft_layout.instruments_from_layout(out)]
        self.assertEqual(ids, ["launcher"])


if __name__ == "__main__":
    unittest.main()
