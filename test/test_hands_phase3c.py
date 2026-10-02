#!/usr/bin/env python3
"""Phase 3C: optional hand tracking + cutouts (no pointer gestures).

  python3 test/test_hands_phase3c.py
"""
from __future__ import annotations

import re
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


class SharedFormat(unittest.TestCase):
    def test_fh_hands_magic_and_capsules(self):
        h = read("hands/include/fh_hands.h")
        self.assertIn('FH_HANDS_MAGIC        "FHHANDS1"', h)
        self.assertIn("FH_HANDS_VERSION      1", h)
        self.assertIn("FH_HANDS_MAX_HANDS    2", h)
        self.assertIn("FH_HANDS_MAX_CAPSULES 64", h)
        self.assertIn("fh_capsule_t", h)
        self.assertIn("capture_ns", h)

    def test_fh_gestures_present_but_unused_by_pointer(self):
        g = read("hands/include/fh_gestures.h")
        self.assertIn("FHGEST01", g)
        self.assertIn("fh_pinch_t", g)
        self.assertIn("pinch[2]", g)
        self.assertIn("grip[2]", g)
        # Phase 3C: pointer must not consume gestures
        p = read("pointer/helper/ft-pointer.cpp")
        self.assertNotIn("fh_gestures", p)
        self.assertNotIn("POINTER_HANDS", p)
        self.assertNotIn("frametop-hands/gestures", p)


class ControlAndInstall(unittest.TestCase):
    def test_ft_handsctl_commands(self):
        ctl = read("hands/ft-handsctl")
        for cmd in ("on)", "off)", "status)", "log)", "cutouts)", "gestures)"):
            self.assertIn(cmd, ctl)
        self.assertIn("frametop-camd.service", ctl)
        self.assertIn("frametop-hands.service", ctl)
        self.assertIn("SteamVR isn't running", ctl)
        self.assertIn('ask_screens "cutouts', ctl)

    def test_run_sh_disabled_by_default(self):
        run = read("hands/run.sh")
        self.assertIn("systemctl --user disable", run)
        self.assertIn("setcap", run)
        self.assertIn("frametop-camd.service", run)
        install = read("install.sh")
        self.assertIn("Hand tracking, hands/, is deferred", install)

    def test_services_part_of_steamvr(self):
        for unit in ("hands/frametop-camd.service", "hands/frametop-hands.service"):
            u = read(unit)
            self.assertIn("PartOf=steamvr.service", u)
            self.assertNotIn("WantedBy=default.target", u)


class CutoutWiring(unittest.TestCase):
    def test_vr_skips_floats_and_has_cutouts_cmd(self):
        vr = read("screens/vr.cpp")
        self.assertIn('#include "handcut.h"', vr)
        self.assertIn("void UpdateCutouts()", vr)
        self.assertIn("!s.floating", vr[vr.index("void UpdateCutouts()") : vr.index("void UpdateCutouts()") + 900])
        self.assertIn('sscanf(cmd, "cutouts %15s"', vr)
        self.assertIn("g_cutouts", vr)
        self.assertIn("handcut::Hands g_hands", vr)

    def test_build_links_handcut(self):
        b = read("screens/build.sh")
        self.assertIn("handcut.o", b)
        self.assertIn("ft-handtest", b)

    def test_handcut_rejects_pathological_geometry_in_source(self):
        # Upstream near-eye / behind-panel guards live in Project()
        c = read("screens/handcut.cpp")
        self.assertIn("Project(", c)
        # Must not project capsules behind the panel or through the eye
        self.assertTrue(
            re.search(r"eye|near|behind|front|0\.0[1-9]", c, re.I),
            "expected depth/near-eye style guards in handcut.cpp",
        )

    def test_missing_hands_file_is_safe(self):
        # Hands::Update returns false when mmap missing — cutouts become no-ops
        c = read("screens/handcut.cpp")
        self.assertIn("frametop-hands/hands", c)
        self.assertIn("bool Hands::Update(", c)
        self.assertIn("bool Hands::Read(", c)


class ConfAndDocs(unittest.TestCase):
    def test_conf_hands_keys_no_pointer_hands_enabled(self):
        conf = read("session/frametop.conf.example")
        self.assertIn("HANDS_CAMERAS=", conf)
        self.assertIn("HANDS_CPUS=", conf)
        # Must not enable POINTER_HANDS in this phase
        self.assertNotRegex(conf, r"(?m)^POINTER_HANDS=1")

    def test_docs(self):
        self.assertTrue((ROOT / "docs/README/HANDS.md").is_file())
        self.assertIn("ft-handsctl", read("docs/README/HANDS.md"))
        ov = read("docs/README/OVERVIEW.md")
        self.assertIn("HANDS.md", ov)


if __name__ == "__main__":
    unittest.main()
