#!/usr/bin/env python3
"""Unit tests for gaze-pointer filtering + button state machine (mirrors screens/vr.cpp).

Run:
  python3 test/test_gaze_pointer.py
"""
from __future__ import annotations

import math
import unittest


class OneEuroFilter:
    """Same math as screens/vr.cpp OneEuroFilter."""

    def __init__(self, min_cutoff=1.0, beta=0.007, d_cutoff=1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.inited = False
        self.x_hat = 0.0
        self.dx_hat = 0.0

    @staticmethod
    def alpha(cutoff, te):
        tau = 1.0 / (2.0 * math.pi * max(cutoff, 1e-6))
        return 1.0 / (1.0 + tau / max(te, 1e-6))

    def reset(self, x=0.0):
        self.inited = True
        self.x_hat = x
        self.dx_hat = 0.0

    def filter(self, x, te):
        if not self.inited:
            self.reset(x)
            return self.x_hat
        te = max(te, 1e-4)
        dx = (x - self.x_hat) / te
        a_d = self.alpha(self.d_cutoff, te)
        self.dx_hat = a_d * dx + (1.0 - a_d) * self.dx_hat
        cutoff = self.min_cutoff + self.beta * abs(self.dx_hat)
        a = self.alpha(cutoff, te)
        self.x_hat = a * x + (1.0 - a) * self.x_hat
        return self.x_hat


class GazePointerButtons:
    """inactive+press → activate (no click); active+press → click."""

    def __init__(self):
        self.active = False
        self.clicks = 0
        self.activates = 0

    def button(self):
        if not self.active:
            self.active = True
            self.activates += 1
            return "activate"
        self.clicks += 1
        return "click"


class Deadzone:
    def __init__(self, px=3.0):
        self.px = px
        self.have = False
        self.x = 0.0
        self.y = 0.0

    def consider(self, x, y):
        if self.have:
            dx, dy = x - self.x, y - self.y
            if dx * dx + dy * dy < self.px * self.px:
                return False
        self.x, self.y = x, y
        self.have = True
        return True


class TestOneEuro(unittest.TestCase):
    def test_stationary_smooths(self):
        f = OneEuroFilter(min_cutoff=1.0, beta=0.007, d_cutoff=1.0)
        out = [f.filter(0.5 + (0.002 if i % 2 else -0.002), 0.011) for i in range(40)]
        # After warm-up, output variance should be below raw jitter amplitude.
        mid = out[20:]
        self.assertLess(max(mid) - min(mid), 0.004)

    def test_fast_move_tracks(self):
        f = OneEuroFilter(min_cutoff=1.0, beta=0.05, d_cutoff=1.0)
        f.filter(0.0, 0.011)
        # Sweep quickly toward 1.0
        y = 0.0
        for i in range(30):
            y = f.filter(min(1.0, i / 10.0), 0.011)
        self.assertGreater(y, 0.7)


class TestButtonMachine(unittest.TestCase):
    def test_activate_then_click(self):
        g = GazePointerButtons()
        self.assertEqual(g.button(), "activate")
        self.assertEqual(g.activates, 1)
        self.assertEqual(g.clicks, 0)
        self.assertEqual(g.button(), "click")
        self.assertEqual(g.button(), "click")
        self.assertEqual(g.clicks, 2)
        self.assertEqual(g.activates, 1)


class TestDeadzone(unittest.TestCase):
    def test_suppresses_tiny(self):
        d = Deadzone(3.0)
        self.assertTrue(d.consider(10, 10))
        self.assertFalse(d.consider(11, 10))  # 1px
        self.assertTrue(d.consider(14, 10))   # 4px

    def test_no_magnetism(self):
        # Deadzone only gates emission; it does not pull toward a target.
        d = Deadzone(3.0)
        d.consider(100, 100)
        self.assertTrue(d.consider(200, 200))
        self.assertEqual((d.x, d.y), (200.0, 200.0))


class TestGpioKeyRoute(unittest.TestCase):
    def test_select_is_gaze(self):
        # Mirror input/input-relay.py gpio_key_route without importing hyphenated module.
        KEY_SELECT, BTN_MISC = 353, 0x100

        def gpio_key_route(code, select_code=KEY_SELECT):
            if code == select_code:
                return "gaze"
            if 0 < code < BTN_MISC:
                return "forward"
            return "drop"

        self.assertEqual(gpio_key_route(353), "gaze")
        self.assertEqual(gpio_key_route(115), "forward")  # KEY_VOLUMEUP
        self.assertEqual(gpio_key_route(114), "forward")  # KEY_VOLUMEDOWN
        self.assertEqual(gpio_key_route(0), "drop")
        self.assertEqual(gpio_key_route(400), "drop")
        # Never forward SELECT even if BTN_MISC ceiling moved in a hypothetical fork.
        self.assertEqual(gpio_key_route(353, select_code=353), "gaze")


class TestEyeSampleHold(unittest.TestCase):
    """Mirrors screens/vr.cpp sticky eye-ray policy (kEyeSampleHoldSec)."""

    HOLD_SEC = 0.45

    def use_ray(self, fresh, since_last_valid, available=True):
        if fresh:
            return "fresh"
        if available and since_last_valid <= self.HOLD_SEC:
            return "held"
        return "none"

    def test_fresh_wins(self):
        self.assertEqual(self.use_ray(True, 1.0), "fresh")

    def test_brief_dropout_holds(self):
        self.assertEqual(self.use_ray(False, 0.1), "held")
        self.assertEqual(self.use_ray(False, 0.45), "held")

    def test_long_dropout_clears(self):
        self.assertEqual(self.use_ray(False, 0.46), "none")
        self.assertEqual(self.use_ray(False, 0.1, available=False), "none")


class TestInstrumentVsScreenPick(unittest.TestCase):
    """Instruments only win when no screen/chrome hit exists."""

    @staticmethod
    def pick(screen_hit, instrument_hit):
        if screen_hit:
            return "screen"
        if instrument_hit:
            return "instrument"
        return "none"

    def test_screen_beats_closer_instrument(self):
        self.assertEqual(self.pick(True, True), "screen")

    def test_instrument_when_empty(self):
        self.assertEqual(self.pick(False, True), "instrument")


class TestAttentionInvalidHold(unittest.TestCase):
    """While focused, lost tracking keeps active target until holdMs elapses."""

    def step(self, focused, focus_ms, hold_ms, dt_ms, valid, hit):
        if not valid:
            if focused:
                focus_ms += dt_ms
                if focus_ms >= hold_ms:
                    focused, focus_ms = False, 0.0
            target = 1.0 if focused else 0.2
            return focused, focus_ms, target
        if hit:
            focus_ms += dt_ms
            if not focused and focus_ms >= 80:
                focused = True
            if focused:
                focus_ms = 0.0
        elif focused:
            focus_ms += dt_ms
            if focus_ms >= hold_ms:
                focused, focus_ms = False, 0.0
        else:
            focus_ms = 0.0
        return focused, focus_ms, (1.0 if focused else 0.2)

    def test_brief_invalid_keeps_active(self):
        focused, ms, target = True, 0.0, 1.0
        for _ in range(10):  # 110 ms of invalid < 400 hold
            focused, ms, target = self.step(focused, ms, 400, 11, False, False)
        self.assertTrue(focused)
        self.assertEqual(target, 1.0)

    def test_long_invalid_releases(self):
        focused, ms, target = True, 0.0, 1.0
        for _ in range(50):  # 550 ms > 400 hold
            focused, ms, target = self.step(focused, ms, 400, 11, False, False)
        self.assertFalse(focused)
        self.assertEqual(target, 0.2)


class TestClickTimeout(unittest.TestCase):
    """Gaze pointer idles out on click silence, not on motion."""

    def idle_out(self, since_click, timeout, motion_happened=False):
        # motion_happened must not affect the decision
        _ = motion_happened
        return since_click >= timeout

    def test_motion_does_not_keep_alive(self):
        self.assertTrue(self.idle_out(10.0, 10.0, motion_happened=True))

    def test_recent_click_keeps(self):
        self.assertFalse(self.idle_out(3.0, 10.0, motion_happened=False))


class TestGazeCalOffset(unittest.TestCase):
    """Mean (expected − measured) UV bias, clamped."""

    @staticmethod
    def mean_offset(pairs, clamp=0.25):
        eu = sum(e - m for e, m in pairs) / len(pairs)
        return max(-clamp, min(clamp, eu))

    def test_systematic_bias(self):
        # Measured always 0.05 left of target → positive U offset.
        pairs = [(0.5, 0.45), (0.2, 0.15), (0.8, 0.75)]
        self.assertAlmostEqual(self.mean_offset(pairs), 0.05, places=5)

    def test_clamp(self):
        pairs = [(0.5, 0.0)] * 5
        self.assertEqual(self.mean_offset(pairs), 0.25)


class TestSteamVrCursorKeys(unittest.TestCase):
    """Keys we hide every frame while Frametop screens are visible."""

    KEYS = (
        "system.pointer",
        "system.pointer.secondary",
        "system.pointer.left",
        "system.pointer.right",
        "system.cursor",
        "system.cursor.secondary",
        "system.cursor.left",
        "system.cursor.right",
    )

    def test_covers_primary_and_hand_variants(self):
        self.assertIn("system.pointer", self.KEYS)
        self.assertIn("system.cursor", self.KEYS)
        self.assertTrue(any(k.endswith(".left") for k in self.KEYS))
        self.assertTrue(any(k.endswith(".right") for k in self.KEYS))


class TestGazeYieldsToController(unittest.TestCase):
    """Gaze stays on until a hand-controller overlay event; then it yields."""

    def decide(self, gaze_active, device_is_hand_controller):
        if not gaze_active:
            return "keep-off"
        if device_is_hand_controller:
            return "deactivate"
        return "keep-on"

    def test_controller_deactivates(self):
        self.assertEqual(self.decide(True, True), "deactivate")

    def test_non_controller_keeps(self):
        self.assertEqual(self.decide(True, False), "keep-on")


class TestRelayGazeToggle(unittest.TestCase):
    """GAZE_POINTER=0 must release gpio grab so SteamVR head laser returns."""

    @staticmethod
    def want_grab(gaze_pointer_enabled, grab_conf=True):
        return bool(gaze_pointer_enabled) and bool(grab_conf)

    def test_off_releases(self):
        self.assertFalse(self.want_grab(False, True))

    def test_on_grabs(self):
        self.assertTrue(self.want_grab(True, True))


class TestLaserTipSize(unittest.TestCase):
    def test_default_visible(self):
        tip = 0.032
        self.assertGreaterEqual(tip, 0.012)
        self.assertLessEqual(tip, 0.08)


class TestHybridPadClamp(unittest.TestCase):
    """Eye offset: deadzone + clamp + gain (stickier hybrid feel)."""

    @staticmethod
    def apply(du, dv, pad=0.08, deadzone=0.50, gain=0.35):
        length = math.hypot(du, dv)
        if length <= pad * deadzone or length < 1e-9:
            return 0.0, 0.0
        cdu, cdv = du, dv
        if length > pad:
            cdu *= pad / length
            cdv *= pad / length
        clen = math.hypot(cdu, cdv)
        live = pad * (1.0 - deadzone)
        t = (clen - pad * deadzone) / live if live > 1e-9 else 1.0
        t = max(0.0, min(1.0, t))
        out = t * pad * gain
        if clen > 1e-9:
            return cdu * (out / clen), cdv * (out / clen)
        return 0.0, 0.0

    def test_centre_dead(self):
        du, dv = self.apply(0.02, 0.0)
        self.assertEqual((du, dv), (0.0, 0.0))

    def test_edge_capped_by_gain(self):
        du, dv = self.apply(0.5, 0.0)
        self.assertAlmostEqual(abs(du), 0.08 * 0.35, places=5)
        self.assertAlmostEqual(dv, 0.0)

    def test_inside_unchanged_shape(self):
        # Just past deadzone: small positive output
        du, dv = self.apply(0.05, 0.0, pad=0.08, deadzone=0.5, gain=1.0)
        self.assertGreater(du, 0.0)
        self.assertLess(du, 0.08)


if __name__ == "__main__":
    unittest.main()
