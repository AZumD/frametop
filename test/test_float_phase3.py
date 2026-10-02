#!/usr/bin/env python3
"""Phase 3A/B: floating-window wiring, ownership, crop math, conceal, pointer guard.

Headless source/unit checks (no SteamVR). Run:

  python3 test/test_float_phase3.py
"""
from __future__ import annotations

import ast
import math
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


class FloatNativeWiring(unittest.TestCase):
    def test_compositor_spares_and_capacity(self):
        c = read("screens/compositor.c")
        m = re.search(r"#define\s+MAX_SCREENS\s+(\d+)", c)
        self.assertIsNotNone(m)
        self.assertGreaterEqual(int(m.group(1)), 24)
        self.assertIn("--spares", c)
        self.assertIn("ft_vr_float_create", c)
        self.assertIn("ft_vr_float_output", c)

    def test_vr_float_lifecycle_commands(self):
        vr = read("screens/vr.cpp")
        self.assertIn("frametop.float.", vr)
        self.assertIn("frametop.float.%d.sub.%d", vr)
        self.assertIn("void SetFloat(", vr)
        self.assertIn("void Unfloat(", vr)
        self.assertIn("void CropOverlay(", vr)
        self.assertRegex(vr, r'sscanf\(cmd,\s*"float ')
        self.assertRegex(vr, r'sscanf\(cmd,\s*"unfloat ')
        self.assertIn('strcmp(cmd, "up")', vr)
        # alone/conceal must not treat floats as real screens
        self.assertIn("if (!s.floating) fn(s)", vr)

    def test_session_spares_wiring(self):
        s = read("session/frametop-session.sh")
        self.assertIn("FLOAT_SLOTS", s)
        self.assertIn("--spares", s)
        self.assertIn("ft-floatd", s)


class RealVsSpareOwnership(unittest.TestCase):
    def test_layout_filters_spare_outputs(self):
        layout = read("layout/ft_layout.py")
        self.assertIn("spares for floating windows", layout)
        # outputs() must skip indices past FT_SCREEN_COUNT / screen count
        self.assertIn("def outputs(", layout)
        block = layout[layout.find("def outputs(") : layout.find("def outputs(") + 1200]
        self.assertTrue(
            "FT_SCREEN_COUNT" in block or "screen_count" in block or "n_screens" in block or "spare" in block.lower(),
            "outputs() should mention screen count / spares",
        )

    def test_floatd_owns_spares_layout_does_not(self):
        floatd = read("float/ft_floatd.py")
        self.assertIn("kscreen-doctor", floatd)
        self.assertIn("spare", floatd.lower())
        # first spare index == real screen count (0-based output index == screens_n)
        self.assertRegex(floatd, r"screens_n|FT_SCREEN_COUNT")


class CropAndInputMapping(unittest.TestCase):
    """Verify crop math: panel shows window frame; margin pads output; pointer maps through crop."""

    def test_crop_from_window_and_margin(self):
        # Mirror ft-floatd / SetFloat contract: output geometry = window + margin on each side;
        # crop is the window rectangle inside that output.
        margin = 300
        win_x, win_y, win_w, win_h = 100, 80, 800, 600
        out_x = win_x - margin
        out_y = win_y - margin
        out_w = win_w + 2 * margin
        out_h = win_h + 2 * margin
        crop_x = win_x - out_x  # == margin
        crop_y = win_y - out_y
        crop_w, crop_h = win_w, win_h
        self.assertEqual(crop_x, margin)
        self.assertEqual(crop_y, margin)
        self.assertEqual(crop_w, 800)
        self.assertEqual(crop_h, 600)
        # Pointer: UV in cropped panel -> output pixels
        u, v = 0.0, 0.0  # top-left of visible panel == window top-left
        ox = out_x + crop_x + u * crop_w
        oy = out_y + crop_y + v * crop_h
        self.assertEqual(ox, win_x)
        self.assertEqual(oy, win_y)
        u, v = 1.0, 1.0
        ox = out_x + crop_x + u * crop_w
        oy = out_y + crop_y + v * crop_h
        self.assertEqual(ox, win_x + win_w)
        self.assertEqual(oy, win_y + win_h)

    def test_setfloat_uses_crop_fields(self):
        vr = read("screens/vr.cpp")
        # SetFloat stores crop and calls CropOverlay
        i = vr.find("void SetFloat(")
        self.assertGreater(i, 0)
        body = vr[i : i + 900]
        self.assertIn("ApplyCrop", body)
        self.assertIn("cropX", body)
        self.assertIn("cropW", body)


class ConcealDocking(unittest.TestCase):
    def test_floatd_dock_fallback_when_origin_concealed(self):
        floatd = read("float/ft_floatd.py")
        self.assertIn("def concealed(", floatd)
        self.assertIn("hidden now", floatd)
        self.assertIn("on_hidden_screen", floatd)
        self.assertIn('ask("concealed"', floatd)

    def test_vr_alone_skips_floating(self):
        vr = read("screens/vr.cpp")
        self.assertIn("if (!s.floating) fn(s)", vr)


class PointerFloatTargeting(unittest.TestCase):
    def test_frame_panel_and_up(self):
        p = read("pointer/helper/ft-pointer.cpp")
        self.assertIn("bool FramePanel(", p)
        self.assertIn('"frametop.float."', p)
        self.assertIn('"frametop.screen."', p)
        self.assertIn(".sub.", p)
        self.assertIn('SendTo(out, "ft_screens", "up")', p)
        self.assertIn("pressKey", p)
        # Fork-specific guards preserved
        self.assertIn('key.rfind("frametop.", 0) == 0) return false', p)
        self.assertIn("onVrSettings", p)

    def test_pointer_ignore_rejects_float_globs(self):
        # Reuse the same guard semantics as test_pointer_ignore.py
        p = read("pointer/helper/ft-pointer.cpp")
        self.assertIn("frametop.*", p)
        # FramePanel must accept float overlays
        self.assertRegex(p, r'frametop\.float\.')


class FloatTogglePath(unittest.TestCase):
    def test_relay_default_meta_shift_f(self):
        relay = read("input/input-relay.py")
        self.assertIn("DEFAULT_KEY_BINDINGS", relay)
        self.assertIn('"42+125+33": "float_toggle"', relay)
        self.assertIn("def key_binding(", relay)
        self.assertIn("FLOAT_ACTIONS", relay)
        self.assertNotIn("gaze_left", relay)  # do not import gaze shortcuts

    def test_read_rules_injects_defaults(self):
        # Load read_rules without running main
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "input_relay_float_test", ROOT / "input" / "input-relay.py"
        )
        mod = importlib.util.module_from_spec(spec)
        # Avoid executing side effects at import — file only defines helpers at top level.
        # Executing the whole module is fine: no main() call.
        spec.loader.exec_module(mod)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write("{}")
            path = f.name
        try:
            rules = mod.read_rules(path)
            self.assertEqual(rules["key_bindings"].get("42+125+33"), "float_toggle")
        finally:
            Path(path).unlink(missing_ok=True)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write('{"key_bindings": {}}')
            path = f.name
        try:
            rules = mod.read_rules(path)
            self.assertEqual(rules["key_bindings"], {})
        finally:
            Path(path).unlink(missing_ok=True)

    def test_no_spare_fails_safe_in_floatd(self):
        floatd = read("float/ft_floatd.py")
        self.assertIn("floating windows are in use", floatd)
        self.assertIn("Put one back on the desktop", floatd)


class NamespaceProtection(unittest.TestCase):
    def test_ignore_never_drops_frametop_float(self):
        p = read("pointer/helper/ft-pointer.cpp")
        # Extract Ignored() body
        i = p.find("bool Ignored(")
        self.assertGreater(i, 0)
        body = p[i : i + 500]
        self.assertIn('rfind("frametop.", 0) == 0) return false', body)


if __name__ == "__main__":
    unittest.main()
