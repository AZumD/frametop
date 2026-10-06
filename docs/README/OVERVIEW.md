# OVERVIEW

Frametop tools and docs for the Steam Frame nested desktop.

## Scripts / modules

| Path | Doc |
|------|-----|
| `scripts/frame-background` | [FRAME-BACKGROUND.md](FRAME-BACKGROUND.md) |
| `scripts/_env.sh` | [SCRIPTS_ENV.md](SCRIPTS_ENV.md) |
| `scripts/openvr_settings.py` | [OPENVR_SETTINGS.md](OPENVR_SETTINGS.md) |
| `scripts/make-equirect-test.py` | [MAKE-EQUIRECT-TEST.md](MAKE-EQUIRECT-TEST.md) |
| `scripts/recover-vr.sh` | [RECOVER-VR.md](RECOVER-VR.md) |
| `scripts/report.sh` | [REPORT.md](REPORT.md) |
| `scripts/probe-eye-attention.sh` | [PROBE-EYE-ATTENTION.md](PROBE-EYE-ATTENTION.md) |
| `scripts/probe-mpris-socket.py` | [PROBE-MPRIS-SOCKET.md](PROBE-MPRIS-SOCKET.md) |
| `scripts/check-live-apply.py` | [CHECK-LIVE-APPLY.md](CHECK-LIVE-APPLY.md) |
| `scripts/rebuild-screens-on-frame.sh` | [REBUILD-SCREENS-ON-FRAME.md](REBUILD-SCREENS-ON-FRAME.md) |
| `scripts/start-desktop-on-frame.sh` | [START-DESKTOP-ON-FRAME.md](START-DESKTOP-ON-FRAME.md) |
| `display-settings/ft_display_settings.py` | [FT_DISPLAY_SETTINGS.md](FT_DISPLAY_SETTINGS.md) |
| `layout/ft_layout.py` | [FT_LAYOUT.md](FT_LAYOUT.md) |
| `session/ft-launch.py` | [FT-LAUNCH.md](FT-LAUNCH.md) |
| `session/ft-game-run` / `ft_game_run.py` | [FT-GAME-RUN.md](FT-GAME-RUN.md) |
| `layout/ft_desktop.py` | [FT_DESKTOP.md](FT_DESKTOP.md) |
| `input/input-relay.py` | [INPUT-RELAY.md](INPUT-RELAY.md) |
| `input/ft-textinput` | [FT_TEXTINPUT.md](FT_TEXTINPUT.md) |
| `pointer/helper/ft-pointer.cpp` | [FT_POINTER.md](FT_POINTER.md) |
| `screens/keyboard.cpp` | [SCREENS_KEYBOARD.md](SCREENS_KEYBOARD.md) |
| `screens/vr.cpp` | [SCREENS_VR.md](SCREENS_VR.md) |
| `screens/test/headless.sh` | [SCREENS_TEST_HEADLESS.md](SCREENS_TEST_HEADLESS.md) |
| `float/ft_floatd.py` | [FT_FLOATD.md](FT_FLOATD.md) |
| `float/ft_apps.py` | [FT_APPS.md](FT_APPS.md) |
| `hands/` | [HANDS.md](HANDS.md) |
| `test/run-unit.sh` | [RUN-UNIT.md](RUN-UNIT.md) |
| Stage 3 Steam→Tovakai game routing | [STEAM_GAME_ROUTING.md](STEAM_GAME_ROUTING.md) |
| `test/_probe_game_routing_*.sh` / `_arm_game_routing_*.sh` / `_verify_game_routing_phase5.sh` | [_PROBE_GAME_ROUTING_PHASE0.md](_PROBE_GAME_ROUTING_PHASE0.md), [_ARM_GAME_ROUTING_PHASE5.md](_ARM_GAME_ROUTING_PHASE5.md) |
| `steam-ui-patches/game-route/` / `_arm_game_route_chooser.sh` | [_ARM_GAME_ROUTE_CHOOSER.md](_ARM_GAME_ROUTE_CHOOSER.md) |
| `test/_pick_game_route_chooser.sh` | [_PICK_GAME_ROUTE_CHOOSER.md](_PICK_GAME_ROUTE_CHOOSER.md) |
| `test/_wait_pick_game_route.sh` | [_WAIT_PICK_GAME_ROUTE.md](_WAIT_PICK_GAME_ROUTE.md) |
| `test/_retest_tovakai_wrap_v2.sh` | [_RETEST_TOVAKAI_WRAP_V2.md](_RETEST_TOVAKAI_WRAP_V2.md) |
| `test/_probe_steam_relaunch_apis.sh` | [_PROBE_STEAM_RELAUNCH_APIS.md](_PROBE_STEAM_RELAUNCH_APIS.md) |
| `test/_probe_steamurl_applies_wrap.sh` | [_PROBE_STEAMURL_APPLIES_WRAP.md](_PROBE_STEAMURL_APPLIES_WRAP.md) |
| `test/_fix_desktop_spares_mismatch.sh` | [_FIX_DESKTOP_SPARES_MISMATCH.md](_FIX_DESKTOP_SPARES_MISMATCH.md) |
| `test/_check_desktop_spares_health.sh` | [_CHECK_DESKTOP_SPARES_HEALTH.md](_CHECK_DESKTOP_SPARES_HEALTH.md) |
| `test/_start_desktop_after_spares_rebuild.sh` | [_START_DESKTOP_AFTER_SPARES_REBUILD.md](_START_DESKTOP_AFTER_SPARES_REBUILD.md) |
| `session/ft-taskbar.py` / `layout/ft_toolbar.py` / `layout/ft_taskbar_model.py` / `screens/desktop_toolbar.inc` (+ dock/taskbar) | [FT-TASKBAR.md](FT-TASKBAR.md), [FT_TASKBAR_MODEL.md](FT_TASKBAR_MODEL.md), [DESKTOP_TOOLBAR.md](DESKTOP_TOOLBAR.md) |
| `screens/app_activity.h` | [APP_ACTIVITY.md](APP_ACTIVITY.md) |
| `test/test_desktop_toolbar.py` / `test_toolbar_dock.py` / `test_taskbar_model.py` / `test_app_activity.py` | [TEST_DESKTOP_TOOLBAR.md](TEST_DESKTOP_TOOLBAR.md), [TEST_TOOLBAR_DOCK.md](TEST_TOOLBAR_DOCK.md), [TEST_TASKBAR_MODEL.md](TEST_TASKBAR_MODEL.md), [TEST_APP_ACTIVITY.md](TEST_APP_ACTIVITY.md) |
| `test/test_overlay_budget_and_games.py` / `test_screen_conceal.py` | [TEST_OVERLAY_BUDGET_AND_GAMES.md](TEST_OVERLAY_BUDGET_AND_GAMES.md), [TEST_SCREEN_CONCEAL.md](TEST_SCREEN_CONCEAL.md) |
| `scripts/sync.sh` | [SYNC.md](SYNC.md) |
| `test/test_ft_layout_lf.py` / `test_launcher_wrappers_lf.py` | [TEST_FT_LAYOUT_LF.md](TEST_FT_LAYOUT_LF.md), [TEST_LAUNCHER_WRAPPERS_LF.md](TEST_LAUNCHER_WRAPPERS_LF.md) |
| `test/_audit_stage_bugfixes*.sh` | [_AUDIT_STAGE_BUGFIXES.md](_AUDIT_STAGE_BUGFIXES.md) |
| `test/_toolbar_overlays.sh` / `_overlay_*_probe*.sh` | [_TOOLBAR_OVERLAYS.md](_TOOLBAR_OVERLAYS.md), [_OVERLAY_ASPECT_PROBE.md](_OVERLAY_ASPECT_PROBE.md) |
| `test/_restore_taskbar_rock_solid.sh` | [_RESTORE_TASKBAR_ROCK_SOLID.md](_RESTORE_TASKBAR_ROCK_SOLID.md) |
| `test/test_chrome_layout.py` | [TEST_CHROME_LAYOUT.md](TEST_CHROME_LAYOUT.md) |
| `test/test_toolbar_reface_on_show.py` | [TEST_TOOLBAR_REFACE_ON_SHOW.md](TEST_TOOLBAR_REFACE_ON_SHOW.md) |

Layout / Spatial Instruments CLI and profile format live in `docs/reference.md` (and `docs/design.md`). **0.1.0 shell:** the spatial desktop toolbar is **on by default** (Start / Tasks / Displays / Tray); `frametop-session.sh` starts `ft-taskbar`, and `ft-layout` restores the toolbar on apply — see [DESKTOP_TOOLBAR.md](DESKTOP_TOOLBAR.md) and [FT-TASKBAR.md](FT-TASKBAR.md). Game hide and OutsideGames lasers share one decision in [APP_ACTIVITY.md](APP_ACTIVITY.md). `ft-layout apply` still pushes visibility, KWin scales, and instruments when the HMD pose is not ready yet (see [FT_LAYOUT.md](FT_LAYOUT.md)). Display Settings → **Background** uses `frame-background`; recover-vr also clears a broken empty `steamvr-pending.path` that can black-screen SteamVR after the boot logo. Launcher Configure writes/removes apps in-process in Display Settings (then host-syncs VR) so remove and the “application not available” warning stay reliable inside distrobox — see [FT_DISPLAY_SETTINGS.md](FT_DISPLAY_SETTINGS.md). SteamVR overlay clients (ft-pointer, ft-screens) probe as Background before Overlay and use `Requisite=steamvr.service` so they cannot bootstrap a rogue vrserver; see `docs/design.md`. Floating windows use spare KWin outputs (`FLOAT_SLOTS`), `ft-floatd`, and `frametop.float.N` panels — see [FT_FLOATD.md](FT_FLOATD.md) and `docs/floating-windows.md`. Optional hand tracking (`hands/`, `ft-handsctl`) and screen hand cutouts are experimental and off by default — see [HANDS.md](HANDS.md).
