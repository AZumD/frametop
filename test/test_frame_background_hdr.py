#!/usr/bin/env python3
"""frame-background converts Radiance .hdr to 8-bit PNG for SteamVR."""
from __future__ import annotations

import importlib.machinery
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "frame-background"


def _load_fb():
    if not SCRIPT.is_file():
        raise unittest.SkipTest(f"missing {SCRIPT}")
    # Extensionless script; SourceFileLoader is required (spec_from_file_location
    # returns loader=None for paths without a known suffix on some Pythons).
    loader = importlib.machinery.SourceFileLoader("frame_background", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None or spec.loader is None:
        raise unittest.SkipTest(f"cannot load {SCRIPT}")
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg required")
class HdrConversionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fb = _load_fb()

    def test_hdr_converts_to_8bit_png(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            src_png = td_path / "src.png"
            hdr = td_path / "sky.hdr"
            out = td_path / "sky.png"
            r = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=blue:s=128x64:d=0.1",
                    "-frames:v",
                    "1",
                    "-update",
                    "1",
                    str(src_png),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            r = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(src_png),
                    "-frames:v",
                    "1",
                    "-update",
                    "1",
                    str(hdr),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(hdr.is_file())
            result = self.fb._convert_to_png(hdr, out)
            self.assertEqual(result, out)
            self.assertTrue(out.is_file())
            data = out.read_bytes()
            self.assertTrue(data.startswith(b"\x89PNG"))
            self.assertEqual(data[24], 8)
            self.assertEqual(data[25], 2)  # truecolor RGB


if __name__ == "__main__":
    raise SystemExit(unittest.main(verbosity=2))
