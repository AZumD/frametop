# TEST_TOOLBAR_DOCK

Scripts: `test/test_toolbar_dock.py`, helpers `test/_run_taskbar_tests.sh`, `test/_build_taskbar.sh`, `test/_deploy_taskbar_dock.sh`, `test/_ds_toolbar_smoke.py` / `test/_ds_toolbar_smoke.sh`

## Purpose

Dependency-light checks for the toolbar body and screen docking (no OpenVR, no Qt), plus the helpers that build, deploy and live-check them on the Frame.

## What `test_toolbar_dock.py` covers

- **Settings** — `sanitize_toolbar` defaults, the screens' follow modes, opacity swap / clamp, scale and timing clamps, follow pin kept only for its own mode, pinned apps de-duplicated.
- **Restore order** — `toolbar_socket_commands`: look before `enable`, pose after, heading turns the saved pose, follow pin last, recentre without a pose, legacy `screen` anchor.
- **Dock persistence** — `parse_dock_state`, `dock_layout` keeps the pre-dock pose and never changes size / curve / opacity, profiles carry and clear `dock`.
- **Dock geometry** — `dock_slots`: centred, above the bar, no overlap between slots, wide groups pushed back to `DOCK_SPAN_RAD`, scale lifts the screens; constants mirror `toolbar_dock.inc` / `vr.cpp`.
- **Dock fly** — `DOCK_ANIM_SEC` / `kDockAnimSec` = 0.450 (profile apply duration); `dock_ease` matches `ft_layout.ease_in_out`; C++ has `DockEase` / `LerpPose` / `BeginDockedTweens` / `TickUndockTweens` wired from `PlaceToolbar`.
- **C++ guards** — the toolbar, screens and instruments share `FollowState, AttentionState, MoveDrag`; no follow / attention math in the toolbar files; drag release re-pins soft follow; dock saves and restores the whole `FollowState` (via `dockTweenRestore` after the undock fly); dock code never sets width / curve / opacity; no `gamepadui` / dashboard ownership; docked screens yield with the toolbar; dock glyphs present; no gaze cursor; `toolbar get` parses with the screens' `parse_get`.
- **Attention model** — interaction wakes at once, gaze needs the dwell.

## Helpers

| Script | Does |
|--------|------|
| `_run_taskbar_tests.sh NAME…` | runs `test/NAME.py` for each name, prints failures |
| `_build_taskbar.sh` | sync + compile ft-screens in the dev container; no restart |
| `_deploy_taskbar_dock.sh` | tests, sync, build, restarts the Frametop desktop, `ft-layout toolbar enable`, then a live dock / undock round trip (pre-dock state reported while docked; size, curve, follow mode unchanged after) |
| `_ds_toolbar_smoke.sh` | loads Display Settings offscreen on the Toolbar page in the dev container with a throwaway HOME and drives the setters |

`_deploy_taskbar_dock.sh` restarts the Frametop desktop (not SteamVR or gamescope); only run it when that's OK.

## Run

```
python3 test/test_toolbar_dock.py
```
