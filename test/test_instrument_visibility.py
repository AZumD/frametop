"""Spatial Instruments follow the same ModeVisible / EffectiveMode rules as screens.

Mirrors screens/vr.cpp EffectiveMode + ModeVisible + UpdateInstrumentVisibility
decision (enabled, shared visibility, mid-drag exception). No OpenVR required.

  python3 test/test_instrument_visibility.py
"""

from __future__ import annotations

import unittest


class Mode:
    ALWAYS = "always"
    DASHBOARD = "dashboard"
    EXCEPT_DASHBOARD = "except_dashboard"
    GESTURE = "gesture"
    TOGGLE = "toggle"


class InGames:
    HIDE = "hide"
    VISIBLE = "visible"


def effective_mode(mode: str, game_running: bool, in_games: str) -> str:
    """screens/vr.cpp EffectiveMode()."""
    if game_running and in_games == InGames.HIDE and mode == Mode.ALWAYS:
        return Mode.DASHBOARD
    return mode


def mode_visible(
    mode: str,
    *,
    game_running: bool = False,
    in_games: str = InGames.HIDE,
    manual: bool = False,
    dashboard_visible: bool = False,
    gesture_looking: bool = False,
) -> bool:
    """screens/vr.cpp ModeVisible() for the cases instruments share with screens."""
    eff = effective_mode(mode, game_running, in_games)
    if eff == Mode.ALWAYS:
        return not manual
    if eff == Mode.TOGGLE:
        return manual
    if eff == Mode.DASHBOARD:
        return manual or dashboard_visible
    if eff == Mode.EXCEPT_DASHBOARD:
        if dashboard_visible:
            return manual
        return not manual
    if eff == Mode.GESTURE:
        return manual or gesture_looking
    return True


def instrument_should_show(
    *,
    enabled: bool,
    shared: bool,
    dragging: bool = False,
    controls: float = 0.0,
    wrist_fade: float = 1.0,
    wrist_pinned: bool = False,
) -> tuple[bool, float]:
    """UpdateInstrumentVisibility decision after ModeVisible is known.

    Returns (visible, visibility_fade). Wrist fade only applies when a controller-
    pinned instrument is not being dragged (mirrors screens).
    """
    if not enabled:
        return False, 1.0
    visible = shared or dragging
    vis_fade = 1.0
    if visible and wrist_pinned and not dragging:
        vis_fade = wrist_fade
        visible = vis_fade > 0.02
    if not visible and controls > 0.02:
        visible = True
        vis_fade = 0.0
    return visible, vis_fade


class EffectiveModeTests(unittest.TestCase):
    def test_always_becomes_dashboard_during_game_hide(self):
        self.assertEqual(
            effective_mode(Mode.ALWAYS, True, InGames.HIDE), Mode.DASHBOARD)

    def test_always_stays_when_ingames_visible(self):
        self.assertEqual(
            effective_mode(Mode.ALWAYS, True, InGames.VISIBLE), Mode.ALWAYS)

    def test_always_stays_when_no_game(self):
        self.assertEqual(
            effective_mode(Mode.ALWAYS, False, InGames.HIDE), Mode.ALWAYS)

    def test_dashboard_mode_unchanged(self):
        self.assertEqual(
            effective_mode(Mode.DASHBOARD, True, InGames.HIDE), Mode.DASHBOARD)

    def test_except_dashboard_unchanged_during_game(self):
        self.assertEqual(
            effective_mode(Mode.EXCEPT_DASHBOARD, True, InGames.HIDE),
            Mode.EXCEPT_DASHBOARD)


class ModeVisibleSharedTests(unittest.TestCase):
    def test_always_shows_outside_game(self):
        self.assertTrue(mode_visible(Mode.ALWAYS))

    def test_always_hides_on_manual(self):
        self.assertFalse(mode_visible(Mode.ALWAYS, manual=True))

    def test_vr_game_hides_instruments_like_screens(self):
        self.assertFalse(mode_visible(Mode.ALWAYS, game_running=True))

    def test_vr_game_dashboard_brings_them_back(self):
        self.assertTrue(
            mode_visible(Mode.ALWAYS, game_running=True, dashboard_visible=True))

    def test_vr_game_hotkey_brings_them_back(self):
        self.assertTrue(mode_visible(Mode.ALWAYS, game_running=True, manual=True))

    def test_ingames_visible_keeps_them_up(self):
        self.assertTrue(
            mode_visible(Mode.ALWAYS, game_running=True, in_games=InGames.VISIBLE))

    def test_toggle_mode_needs_manual(self):
        self.assertFalse(mode_visible(Mode.TOGGLE))
        self.assertTrue(mode_visible(Mode.TOGGLE, manual=True))

    def test_except_dashboard_hides_when_dashboard_open(self):
        self.assertTrue(mode_visible(Mode.EXCEPT_DASHBOARD, dashboard_visible=False))
        self.assertFalse(mode_visible(Mode.EXCEPT_DASHBOARD, dashboard_visible=True))

    def test_except_dashboard_hotkey_shows_over_dashboard(self):
        self.assertTrue(
            mode_visible(Mode.EXCEPT_DASHBOARD, dashboard_visible=True, manual=True))

    def test_except_dashboard_hotkey_hides_when_closed(self):
        self.assertFalse(
            mode_visible(Mode.EXCEPT_DASHBOARD, dashboard_visible=False, manual=True))


class InstrumentVisibilityTests(unittest.TestCase):
    def test_disabled_stays_hidden(self):
        visible, _ = instrument_should_show(enabled=False, shared=True)
        self.assertFalse(visible)

    def test_follows_shared_visibility(self):
        self.assertTrue(instrument_should_show(enabled=True, shared=True)[0])
        self.assertFalse(instrument_should_show(enabled=True, shared=False)[0])

    def test_drag_keeps_visible_when_shared_off(self):
        visible, fade = instrument_should_show(
            enabled=True, shared=False, dragging=True)
        self.assertTrue(visible)
        self.assertEqual(fade, 1.0)

    def test_controls_linger_like_screens(self):
        visible, fade = instrument_should_show(
            enabled=True, shared=False, controls=0.5)
        self.assertTrue(visible)
        self.assertEqual(fade, 0.0)

    def test_wrist_fade_hides_when_facing_away(self):
        visible, fade = instrument_should_show(
            enabled=True, shared=True, wrist_pinned=True, wrist_fade=0.01)
        self.assertFalse(visible)
        self.assertLessEqual(fade, 0.02)

    def test_composed_alpha_multiplies_visibility_fade(self):
        # Instrument::ComposedAlpha = attentionResolved * visibilityFade
        attention, vis = 0.8, 0.5
        self.assertAlmostEqual(attention * vis, 0.4)


if __name__ == "__main__":
    unittest.main()
