#!/usr/bin/env python3
"""Tests for Steam Frame custom SteamVR background support (run on the Frame)."""
from __future__ import annotations

import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
MAKE = SCRIPTS / "make-equirect-test.py"
FB = SCRIPTS / "frame-background"
OVS = SCRIPTS / "openvr_settings.py"
TEST_PNG = (
    Path.home()
    / ".config/openvr/config/frametop-backgrounds/frametop-test-equirect.png"
)
COMP_LOG = Path.home() / ".local/share/Steam/logs/vrcompositor.txt"
STOCK_NM = "/opt/steamvr/resources/backgrounds/night_mountains.png"
STOCK_AS = "/opt/steamvr/resources/backgrounds/aurorasky.png"


def _on_frame() -> bool:
    try:
        text = Path("/etc/os-release").read_text()
    except OSError:
        return False
    return 'ID=steamos' in text and 'VARIANT_ID="vr"' in text


def _run(cmd: list[str], timeout: float = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, check=False
    )


@unittest.skipUnless(_on_frame(), "requires Steam Frame (SteamOS VR) with SteamVR running")
class FrameBackgroundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not OVS.is_file():
            raise unittest.SkipTest(f"missing {OVS}")
        # Sanity: can talk to SteamVR
        r = _run([sys.executable, str(OVS), "get-int", "steamvr", "environmentMode"])
        if r.returncode != 0:
            raise unittest.SkipTest(f"OpenVR settings unavailable: {r.stderr}")
        cls._prev_bg = _run(
            [sys.executable, str(OVS), "get-string", "steamvr", "background"]
        ).stdout.strip()
        cls._prev_mode = _run(
            [sys.executable, str(OVS), "get-int", "steamvr", "environmentMode"]
        ).stdout.strip()

    @classmethod
    def tearDownClass(cls) -> None:
        # Restore prior settings
        if getattr(cls, "_prev_bg", None):
            _run(
                [
                    sys.executable,
                    str(OVS),
                    "set-string",
                    "steamvr",
                    "background",
                    cls._prev_bg,
                ]
            )
        if getattr(cls, "_prev_mode", None) is not None:
            _run(
                [
                    sys.executable,
                    str(OVS),
                    "set-int",
                    "steamvr",
                    "environmentMode",
                    cls._prev_mode,
                ]
            )

    def test_01_generate_equirect(self) -> None:
        r = _run([sys.executable, str(MAKE), "-o", str(TEST_PNG), "--width", "2048"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(TEST_PNG.is_file())
        data = TEST_PNG.read_bytes()
        self.assertTrue(data.startswith(b"\x89PNG"))
        import struct

        w, h = struct.unpack(">II", data[16:24])
        self.assertEqual(w, 2048)
        self.assertEqual(h, 1024)

    def _skybox_load_count(self) -> int:
        if not COMP_LOG.is_file():
            return 0
        return COMP_LOG.read_text(errors="replace").count(
            "Loading background skybox texture async"
        )

    def _compositor_reloads_skyboxes(self) -> bool:
        """True if a stock path change produces a compositor skybox log line."""
        before = self._skybox_load_count()
        before_lines = (
            COMP_LOG.read_text(errors="replace").count("\n") if COMP_LOG.is_file() else 0
        )
        _run(
            [
                sys.executable,
                str(OVS),
                "set-int",
                "steamvr",
                "environmentMode",
                "1",
            ]
        )
        time.sleep(0.5)
        _run(
            [
                sys.executable,
                str(OVS),
                "set-string",
                "steamvr",
                "background",
                STOCK_AS,
            ]
        )
        _run(
            [
                sys.executable,
                str(OVS),
                "set-int",
                "steamvr",
                "environmentMode",
                "0",
            ]
        )
        deadline = time.time() + 6
        while time.time() < deadline:
            if self._skybox_load_count() > before:
                return True
            text = COMP_LOG.read_text(errors="replace")
            if STOCK_AS in "\n".join(text.splitlines()[before_lines:]):
                return True
            time.sleep(0.25)
        return False

    def test_02_set_custom_reloads_compositor(self) -> None:
        unique = TEST_PNG.with_name(f"frametop-test-{int(time.time())}.png")
        r = _run([sys.executable, str(MAKE), "-o", str(unique), "--width", "2048"])
        self.assertEqual(r.returncode, 0, r.stderr)

        r = _run([sys.executable, str(FB), "set", str(unique)])
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        st = _run([sys.executable, str(FB), "status"])
        self.assertEqual(st.returncode, 0)
        self.assertIn("environmentMode: 0 (image)", st.stdout)
        self.assertIn(unique.name, st.stdout)

        # Settings are authoritative even if the compositor is idle (HMD off).
        live = _run(
            [sys.executable, str(OVS), "get-string", "steamvr", "background"]
        ).stdout.strip()
        self.assertTrue(live.endswith(unique.name), live)

        if not self._compositor_reloads_skyboxes():
            self.skipTest(
                "compositor not logging skybox reloads right now (HMD idle?); "
                "settings path verified"
            )

        before_lines = COMP_LOG.read_text(errors="replace").count("\n")
        # Force another apply of a fresh copy so the log check is about *this* call.
        unique2 = TEST_PNG.with_name(f"frametop-test-{int(time.time())}-b.png")
        unique2.write_bytes(unique.read_bytes())
        r = _run([sys.executable, str(FB), "set", str(unique2)])
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        deadline = time.time() + 12
        found = False
        while time.time() < deadline:
            tail = "\n".join(
                COMP_LOG.read_text(errors="replace").splitlines()[before_lines:]
            )
            if unique2.name in tail and "Loading background skybox" in tail:
                found = True
                break
            time.sleep(0.25)
        self.assertTrue(found, "compositor did not log skybox load while active")

    def test_03_stock_aliases_and_aurora(self) -> None:
        r = _run([sys.executable, str(FB), "set", "aurorasky"])
        self.assertEqual(r.returncode, 0, r.stderr)
        time.sleep(0.5)
        bg = _run(
            [sys.executable, str(OVS), "get-string", "steamvr", "background"]
        ).stdout.strip()
        self.assertEqual(bg, STOCK_AS)

        r = _run([sys.executable, str(FB), "aurora"])
        self.assertEqual(r.returncode, 0, r.stderr)
        mode = _run(
            [sys.executable, str(OVS), "get-int", "steamvr", "environmentMode"]
        ).stdout.strip()
        self.assertEqual(mode, "1")

        r = _run([sys.executable, str(FB), "set", "night_mountains"])
        self.assertEqual(r.returncode, 0, r.stderr)
        mode = _run(
            [sys.executable, str(OVS), "get-int", "steamvr", "environmentMode"]
        ).stdout.strip()
        bg = _run(
            [sys.executable, str(OVS), "get-string", "steamvr", "background"]
        ).stdout.strip()
        self.assertEqual(mode, "0")
        self.assertEqual(bg, STOCK_NM)


if __name__ == "__main__":
    # Allow running against a synced copy path override
    if os.environ.get("FRAME_REPO"):
        pass
    raise SystemExit(unittest.main(verbosity=2))
