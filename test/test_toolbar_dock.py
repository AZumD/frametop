#!/usr/bin/env python3
"""Toolbar body (shared follow / attention / move bar) and screen docking — no OpenVR.

Covers the layout schema, the socket restore order, dock persistence through layouts and
profiles, the dock slot geometry, and static guards on the C++ (shared behaviour, no
duplicated follow math, no Valve dashboard ownership).

Run:
  python3 test/test_toolbar_dock.py
"""
from __future__ import annotations

import math
import os
import re
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "layout"))
import ft_toolbar  # noqa: E402
import ft_layout  # noqa: E402


def read(rel: str) -> str:
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def turn_yaw(v, yaw):
    return ft_layout.turn_yaw(v, yaw)


class ToolbarSettings(unittest.TestCase):
    def test_defaults(self):
        tb = ft_toolbar.sanitize_toolbar({"enabled": True})
        self.assertEqual(tb["anchor"], "world")
        self.assertEqual(tb["scale"], 1.0)
        self.assertTrue(tb["attention"]["enabled"])
        self.assertFalse(tb["follow_deadzone"]["enabled"])
        self.assertEqual((tb["active_opacity"], tb["idle_opacity"]), (1.0, 1.0))  # opaque by default
        self.assertEqual(tb["pinned_apps"], [])

    def test_follow_modes_shared_with_screens(self):
        for mode in ("world", "head", "head-rigid", "yaw-follow", "position-follow"):
            self.assertIn(mode, ft_layout.ANCHOR_MODES)
            self.assertEqual(ft_toolbar.sanitize_toolbar({"anchor": mode})["anchor"], mode)
        self.assertEqual(ft_toolbar.sanitize_toolbar({"anchor": "bogus"})["anchor"], "world")

    def test_opacity_swapped_and_clamped(self):
        tb = ft_toolbar.sanitize_toolbar({"active_opacity": 0.3, "idle_opacity": 0.9})
        self.assertEqual((tb["active_opacity"], tb["idle_opacity"]), (0.9, 0.3))
        tb = ft_toolbar.sanitize_toolbar({"active_opacity": 4, "idle_opacity": -1})
        self.assertEqual((tb["active_opacity"], tb["idle_opacity"]), (1.0, 0.0))

    def test_scale_and_timing_clamped(self):
        tb = ft_toolbar.sanitize_toolbar({"scale": 9, "attention": {"enabled": False, "in_ms": 1}})
        self.assertEqual(tb["scale"], 2.0)
        self.assertFalse(tb["attention"]["enabled"])
        self.assertEqual(tb["attention"]["in_ms"], 20.0)

    def test_pin_only_kept_for_matching_follow_mode(self):
        rel = [1, 0, 0, 0, 0, 1, 0, -0.4, 0, 0, 1, -0.8]
        tb = ft_toolbar.sanitize_toolbar({"anchor": "yaw-follow", "pin": {"anchor": "yaw-follow", "rel": rel}})
        self.assertEqual(tb["pin"]["rel"], [float(v) for v in rel])
        tb = ft_toolbar.sanitize_toolbar({"anchor": "world", "pin": {"anchor": "yaw-follow", "rel": rel}})
        self.assertNotIn("pin", tb)

    def test_pinned_apps_dedupe(self):
        tb = ft_toolbar.sanitize_toolbar({"pinned_apps": ["a.desktop", "a.desktop", "", "../x", "b.desktop"]})
        self.assertEqual(tb["pinned_apps"], ["a.desktop", "b.desktop"])


class ToolbarRestoreOrder(unittest.TestCase):
    def cmds(self, raw, eye=(0, 1.6, 0), heading=0.0):
        tb = ft_toolbar.sanitize_toolbar(raw)
        return ft_toolbar.toolbar_socket_commands(tb, eye, heading, turn_yaw)

    def test_disabled(self):
        self.assertEqual(self.cmds({"enabled": False}), ["toolbar disable"])

    def test_look_before_enable_pose_after(self):
        c = self.cmds({"enabled": True, "scale": 1.2, "pos": [0, -0.4, -0.8], "face": [0, 0]})
        en = c.index("toolbar enable")
        self.assertLess(c.index("toolbar scale 1.200"), en)
        self.assertTrue(any(x.startswith("toolbar opacity") for x in c[:en]))
        place = [i for i, x in enumerate(c) if x.startswith("toolbar place")]
        self.assertEqual(len(place), 1)
        self.assertGreater(place[0], en)
        self.assertIn("toolbar place 0.0000 1.2000 -0.8000", c[place[0]])

    def test_heading_turns_pose(self):
        c = self.cmds({"enabled": True, "pos": [0, -0.4, -1.0], "face": [0, 0]}, heading=90.0)
        place = next(x for x in c if x.startswith("toolbar place")).split()
        self.assertAlmostEqual(float(place[2]), -1.0, places=3)  # x: forward turned left
        self.assertAlmostEqual(float(place[5]), 90.0, places=2)

    def test_follow_pin_last(self):
        rel = [1, 0, 0, 0, 0, 1, 0, -0.4, 0, 0, 1, -0.8]
        c = self.cmds({"enabled": True, "anchor": "head", "pos": [0, -0.4, -0.8], "face": [0, 0],
                       "pin": {"anchor": "head", "rel": rel}})
        self.assertTrue(c[-1].startswith("toolbar pin head 1.00000"))

    def test_no_pose_recenters(self):
        c = self.cmds({"enabled": True, "anchor": "yaw-follow"})
        self.assertIn("toolbar recenter", c)
        self.assertEqual(c[-1], "toolbar pin yaw-follow")

    def test_legacy_screen_anchor(self):
        c = self.cmds({"enabled": True, "anchor": "screen", "screen": 2})
        self.assertIn("toolbar attach screen 2", c)


class DockPersistence(unittest.TestCase):
    def layout(self):
        return {"screens": [{"size": [1920, 1080], "pos": [0, 0, -2], "face": [0, 0]},
                            {"size": [1920, 1080], "pos": [1, 0, -2], "face": [-20, 0]}]}

    def test_parse_dock_state(self):
        self.assertEqual(ft_layout.parse_dock_state("ok 2 1:0 2:1"), {1: 0, 2: 1})
        self.assertEqual(ft_layout.parse_dock_state("ok 0"), {})
        with self.assertRaises(RuntimeError):
            ft_layout.parse_dock_state("error nope")

    def test_dock_layout_keeps_pre_dock_pose(self):
        lay = ft_layout.dock_layout(self.layout(), {2: 0})
        self.assertEqual(lay["screens"][1]["dock"], {"docked": True, "slot": 0})
        self.assertEqual(lay["screens"][1]["pos"], [1, 0, -2])  # pre-dock state untouched
        self.assertNotIn("dock", lay["screens"][0])
        lay = ft_layout.dock_layout(lay, {})
        self.assertNotIn("dock", lay["screens"][1])

    def test_dock_never_changes_size_curve_opacity(self):
        before = self.layout()
        before["screens"][0].update({"metres": 1.94, "curve": 2.5, "active_opacity": 0.8, "idle_opacity": 0.4})
        after = ft_layout.dock_layout(before, {1: 3})["screens"][0]
        for k in ("metres", "curve", "active_opacity", "idle_opacity", "size"):
            self.assertEqual(after[k], before["screens"][0][k])

    def test_profiles_carry_dock(self):
        entry = {"pos": [0, 0, -2], "face": [0, 0], "dock": {"docked": True, "slot": 1}}
        self.assertEqual(ft_layout.spatial_screen(entry)["dock"], {"docked": True, "slot": 1})
        self.assertNotIn("dock", ft_layout.spatial_screen({"pos": [0, 0, -2], "dock": {"docked": False}}))
        lay = self.layout()
        lay["screens"][0]["dock"] = {"docked": True, "slot": 0}
        profile = {"screens": [ft_layout.spatial_screen({"pos": [0, 0, -2], "face": [0, 0]}),
                               ft_layout.spatial_screen(entry)]}
        merged = ft_layout.merge_profile_into_layout(lay, profile)
        self.assertNotIn("dock", merged["screens"][0])  # the profile undocks it
        self.assertEqual(merged["screens"][1]["dock"]["slot"], 1)

    def test_profiles_carry_toolbar(self):
        lay = self.layout()
        lay["toolbar"] = {"enabled": True, "anchor": "yaw-follow", "pos": [0.1, -0.3, -0.9], "face": [5, 0],
                          "scale": 1.2, "active_opacity": 1.0, "idle_opacity": 0.4, "pinned_apps": ["a.desktop"]}
        snap = ft_layout.profile_from_layout(lay)
        self.assertEqual(snap["toolbar"]["pos"], [0.1, -0.3, -0.9])
        self.assertEqual(snap["toolbar"]["pinned_apps"], ["a.desktop"])
        other = self.layout()
        other["toolbar"] = {"enabled": True, "pos": [0, -0.5, -1], "face": [0, 0], "scale": 0.8}
        merged = ft_layout.merge_profile_into_layout(other, snap)
        tb = merged["toolbar"]
        self.assertEqual((tb["anchor"], tb["scale"], tb["idle_opacity"]), ("yaw-follow", 1.2, 0.4))
        self.assertEqual(tb["pos"], [0.1, -0.3, -0.9])

    def test_old_profile_keeps_current_toolbar(self):
        lay = self.layout()
        lay["toolbar"] = {"enabled": True, "pos": [0, -0.5, -1], "face": [0, 0], "scale": 0.8}
        snap = ft_layout.profile_from_layout(self.layout())
        snap.pop("toolbar", None)
        merged = ft_layout.merge_profile_into_layout(lay, snap)
        self.assertEqual(merged["toolbar"]["scale"], 0.8)

    def test_screen_dock_sanitize(self):
        self.assertIsNone(ft_layout.screen_dock({}))
        self.assertEqual(ft_layout.screen_dock({"dock": {"docked": 1, "slot": "x"}}), {"docked": True, "slot": 0})


class DockGeometry(unittest.TestCase):
    def screens(self, *widths):
        return [{"metres": w, "height": w * 9 / 16, "chrome": 0.2, "grip": 0.05} for w in widths]

    def test_single_centred_above_bar(self):
        (s,) = ft_toolbar.dock_slots(self.screens(1.2), curve_m=0.8)
        self.assertAlmostEqual(s["u"], 0.0)
        bottom_of_controls = s["lift"] - 1.2 * 9 / 16 / 2 - ft_toolbar.dock_clearance(0.2, 0.05)
        self.assertGreater(bottom_of_controls, ft_toolbar.BAR_H_M / 2)  # never overlaps the bar

    def test_slots_do_not_overlap(self):
        slots = ft_toolbar.dock_slots(self.screens(1.2, 0.6, 1.94), curve_m=0.8)
        for a, b in zip(slots, slots[1:]):
            self.assertGreaterEqual(b["left"] - a["right"], ft_toolbar.DOCK_SPACING_M - 1e-9)
        self.assertAlmostEqual(slots[0]["left"], -slots[-1]["right"])  # centred group

    def test_wide_group_pushed_back(self):
        slots = ft_toolbar.dock_slots(self.screens(1.94, 1.94), curve_m=0.8)
        r = slots[0]["radius"]
        self.assertGreater(r, 0.8)
        span = (slots[-1]["right"] - slots[0]["left"]) / r
        self.assertLessEqual(span, ft_toolbar.DOCK_SPAN_RAD + 1e-9)

    def test_scale_lifts_screens(self):
        a = ft_toolbar.dock_slots(self.screens(1.0), 0.8, scale=1.0)[0]["lift"]
        b = ft_toolbar.dock_slots(self.screens(1.0), 0.8, scale=2.0)[0]["lift"]
        self.assertAlmostEqual(b - a, ft_toolbar.BAR_H_M / 2)

    def test_mirrors_cpp_constants(self):
        dock = read("screens/toolbar_dock.inc")
        self.assertIn(f"kDockLift = {ft_toolbar.DOCK_LIFT_M}", dock)
        self.assertIn(f"kDockSpacing = {ft_toolbar.DOCK_SPACING_M}", dock)
        self.assertIn(f"kDockSpanRad = {ft_toolbar.DOCK_SPAN_RAD}", dock)
        vr = read("screens/vr.cpp")
        self.assertIn(f"kGapFrac = {ft_toolbar.CHROME_GAP_FRAC}", vr)


class CppGuards(unittest.TestCase):
    def setUp(self):
        self.tb = read("screens/desktop_toolbar.inc")
        self.dock = read("screens/toolbar_dock.inc")
        self.vr = read("screens/vr.cpp")
        self.spatial = read("screens/spatial.inc")

    def test_visual_polish(self):
        # Opaque by default, no group plates, cells the bar's colour, an arch-shaped tilted bar.
        self.assertIn("idleOpacity = 1.f;", self.tb)
        self.assertNotIn("plate", self.tb.lower())
        self.assertIn("kArchDeg", self.tb)
        self.assertIn("UploadToolbarBacking(arch);", self.tb)
        self.assertIn("ToolbarOnArch(arch, bx,", self.tb)
        self.assertIn("ToolbarOnArch(Arch(), anchorU", read("screens/toolbar_taskbar.inc"))
        self.assertIn("- ToolbarStyle::kTiltBackDeg", self.tb)
        self.assertIn("set(g_toolbar.backing, a);", self.tb)
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "screens", "assets", "start-icon.png")))
        self.assertIn("StartTileTexture", read("screens/toolbar_taskbar.inc"))
        # App icons sit a little below tile centre (arch roof bias).
        self.assertIn("oy = (n - N) / 2 + 2;", read("screens/toolbar_taskbar.inc"))
        self.assertIn("kCellBandNudge = 0.08", self.tb)
        self.assertIn("nudge * std::sin(phi)", self.tb)

    def test_task_rebuild_keeps_backing(self):
        # Launching from Start rebuilds the task strip without destroying the bar backing
        # (a blank backing was the footgun that made the bar vanish).
        self.assertIn("void DestroyToolbarCells()", self.tb)
        self.assertIn("DestroyToolbarCells();", self.tb)
        self.assertIn("cellPool", self.tb)
        self.assertIn("ToolbarCellOverlay(", self.tb)
        cells = self.tb.split("void DestroyToolbarCells()", 1)[1].split("\n}", 1)[0]
        self.assertIn("HideOverlay", cells)
        self.assertNotIn("KillOverlay", cells)
        self.assertIn("ArchTexture(arch, texW, texH)", self.tb)
        self.assertNotIn("start from a blank texture", self.tb)
        self.assertIn("interactUntil", self.tb)
        self.assertIn("g_toolbar.interactUntil = g_tick + 45", read("screens/toolbar_taskbar.inc"))
        self.assertIn("ToolbarOnArch(arch, bx, TS(ToolbarStyle::kBtnDz), /*roll=*/true)", self.tb)
        self.assertIn("ToolbarCurvature(g_toolbar.metres)", self.tb)
        self.assertIn("RefaceToolbarBtn(b);", self.tb.split("void RebuildToolbarForTasks()")[1].split("void TickTaskbar")[0])

    def test_docked_screens_keep_head_distance_arc(self):
        # The arch is the bar's outline only; the horizontal arc stays the head distance.
        self.assertIn("g_toolbar.curve", self.dock)
        self.assertIn("const double r = g_toolbar.curve;", self.tb)

    def test_shared_bodies(self):
        self.assertIn("struct DesktopToolbar : FollowState, AttentionState, MoveDrag", self.tb)
        self.assertIn("struct Screen : FollowState, AttentionState, MoveDrag", self.vr)
        self.assertIn("struct Instrument : FollowState, AttentionState, MoveDrag", self.vr)

    def test_no_duplicated_follow_or_attention_math(self):
        for src in (self.tb, self.dock):
            self.assertNotIn("SmoothToward(", src)
            self.assertNotIn("PushFollowLock(", src)
            self.assertNotIn("std::exp(-dt", src)
        for fn in ("StepSoftFollow(g_toolbar", "StepAttention(g_toolbar", "BeginMoveDrag(g_toolbar",
                   "EndMoveDrag(g_toolbar", "MoveDragPose(g_toolbar"):
            self.assertIn(fn, self.tb)

    def test_drag_release_keeps_follow(self):
        body = self.spatial.split("bool EndMoveDrag", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("RepinInPlace(f, restore)", body)

    def test_dock_saves_and_restores_follow_state(self):
        self.assertIn("s.preDock = static_cast<const FollowState &>(s);", self.dock)
        # Undock eases first, then restores FollowState from dockTweenRestore (= preDock).
        self.assertIn("s.dockTweenRestore = s.preDock;", self.dock)
        self.assertIn("static_cast<FollowState &>(s) = s.dockTweenRestore;", self.dock)

    def test_dock_animates_like_profile_apply(self):
        # Same duration + cosine ease as layout/ft_layout.py profile transitions.
        self.assertEqual(ft_toolbar.DOCK_ANIM_SEC, 0.450)
        self.assertAlmostEqual(ft_layout.DEFAULT_PROFILE_DURATION_MS / 1000.0, ft_toolbar.DOCK_ANIM_SEC)
        self.assertIn(f"kDockAnimSec = {ft_toolbar.DOCK_ANIM_SEC}", self.dock)
        self.assertIn("DockEase", self.dock)
        self.assertIn("LerpPose", self.dock)
        self.assertIn("BeginDockedTweens", self.dock)
        self.assertIn("TickUndockTweens", self.dock)
        self.assertIn("TickUndockTweens()", self.tb)
        # Ease curve matches profile apply.
        self.assertAlmostEqual(ft_toolbar.dock_ease(0.0), 0.0)
        self.assertAlmostEqual(ft_toolbar.dock_ease(1.0), 1.0)
        self.assertAlmostEqual(ft_toolbar.dock_ease(0.5), 0.5)
        self.assertAlmostEqual(ft_toolbar.dock_ease(0.25), ft_layout.ease_in_out(0.25))
        self.assertLess(ft_toolbar.dock_ease(0.25), 0.25)  # ease-in is slow at start
        self.assertGreater(ft_toolbar.dock_ease(0.75), 0.75)

    def test_dock_only_moves(self):
        for forbidden in ("s.metres =", "s->metres =", "s.curve =", "s->curve =", "Opacity(", "SetWidth("):
            self.assertNotIn(forbidden, self.dock)

    def test_no_valve_dashboard_ownership(self):
        for src in (self.tb, self.dock):
            self.assertNotIn("gamepadui", src.lower())
            self.assertNotIn("SetOverlayTransformOverlayRelative", src)
            self.assertNotIn("ShowDashboard", src)

    def test_makechrome_sets_mouse_scale(self):
        # stage2 f64f603: default 1x1 mouse scale makes a wide bar a huge invisible laser pane.
        fn = self.vr.split("vr::VROverlayHandle_t MakeChrome(", 1)[1].split("\n}", 1)[0]
        self.assertIn("SetOverlayMouseScale", fn)
        self.assertIn("float(w)", fn)
        self.assertIn("float(h)", fn)
        self.assertIn("UploadToolbarBacking", self.tb)
        self.assertIn("SetOverlayMouseScale(g_toolbar.backing", self.tb)

    def test_docked_group_yields_with_toolbar(self):
        self.assertIn("if (s.docked && !ToolbarWanted()) visible = false;", self.vr)
        self.assertIn("return !vr::VROverlay()->IsDashboardVisible() && ModeVisible();", self.tb)

    def test_dock_button_glyphs(self):
        # SteamVR's Minimize (dock) and Popout (undock) glyph outlines, re-drawn as polygons.
        self.assertIn("kDockChevron", self.vr)
        self.assertIn("kUndockArrow", self.vr)
        self.assertIn('"frametop.screen.', self.vr)

    def test_no_gaze_cursor(self):
        self.assertNotIn("cursor", self.tb.lower().replace("no gaze cursor", ""))

    def test_get_reply_matches_screen_parser(self):
        g = ft_layout.parse_get("ok 0.1 1.2 -0.8  1 0 0  0 1 0  0 0 1  0.9 0.09 0.85 1.000 0.550 yaw-follow"
                                " 1 0 0 0 0 1 0 -0.4 0 0 1 -0.8")
        self.assertEqual(g["anchor"], "yaw-follow")
        self.assertEqual(len(g["rel"]), 12)
        self.assertAlmostEqual(g["idle_opacity"], 0.55)


class AttentionModel(unittest.TestCase):
    """StepAttention semantics (spatial.inc), modelled step by step."""

    def step(self, st, hit, dt, awake=False):
        on = hit or awake
        if on:
            st["ms"] += dt * 1000
            if awake or (not st["focused"] and st["ms"] >= st["dwell"]):
                st["focused"] = True
            if st["focused"]:
                st["ms"] = 0
        elif st["focused"]:
            st["ms"] += dt * 1000
            if st["ms"] >= st["hold"]:
                st["focused"], st["ms"] = False, 0
        else:
            st["ms"] = 0
        target = st["active"] if st["focused"] else st["idle"]
        tau = (st["in"] if st["focused"] else st["out"]) / 1000
        st["r"] += (target - st["r"]) * (1 - math.exp(-dt / tau))

    def state(self):
        return {"ms": 0, "focused": False, "dwell": 80, "hold": 400, "in": 150, "out": 250,
                "active": 1.0, "idle": 0.3, "r": 0.3}

    def test_interaction_wakes_immediately(self):
        st = self.state()
        self.step(st, False, 0.011, awake=True)
        self.assertTrue(st["focused"])

    def test_gaze_needs_dwell(self):
        st = self.state()
        self.step(st, True, 0.05)
        self.assertFalse(st["focused"])
        self.step(st, True, 0.05)
        self.assertTrue(st["focused"])

    def test_cpp_has_awake(self):
        self.assertIn("bool StepAttention(AttentionState &a, bool hit, double dt, bool awake = false)",
                      read("screens/spatial.inc"))
        self.assertIn("StepAttention(g_toolbar, hit, dt, ToolbarInteracting())", read("screens/desktop_toolbar.inc"))


if __name__ == "__main__":
    unittest.main()
