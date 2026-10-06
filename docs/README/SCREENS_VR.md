# SCREENS_VR

Module: `screens/vr.cpp` / `screens/vr.h` (built into `ft-screens` by `screens/build.sh`)

## Purpose

OpenVR side of Frametop: virtual screen and floating-window panels, chrome, Spatial Instruments, visibility modes, and SteamVR game detection. DMA-BUF frames become overlay textures; lasers and the 3D mouse hit those overlays and map into KWin seats.

## Wiring

- **Screens** — `frametop.screen.N` plus under-chrome (bar, curve, roll, resize, anchor, toolbar dock). Profile digits are not under screens; Displays on the spatial toolbar owns them. `MakePanel` purges any leftover `*.slotN` overlays from older builds. `PlaceChrome` always sizes the dock button to grip (OpenVR’s default width is huge).
- **Spatial toolbar** — `desktop_toolbar.inc` (+ `toolbar_taskbar.inc` / `toolbar_dock.inc` / `spatial.inc`): Frametop-owned SteamVR-grammar bar (`frametop.toolbar.*`). Fed by host `ft-taskbar`; layout via `ft-layout toolbar …`. See [DESKTOP_TOOLBAR.md](DESKTOP_TOOLBAR.md), [FT-TASKBAR.md](FT-TASKBAR.md). `ShowToolbar(true)` re-faces every cell so Hide/Show (dashboard yield) cannot leave blank icons.
- **Floating windows** — spare outputs create only `frametop.float.N` at start. Bar / dock / close / resize chrome is created in `EnsureFloatChrome` on the first `float` command and destroyed in `ReleaseFloatChrome` on `unfloat`, so idle float slots do not exhaust SteamVR’s overlay limit (which also blocks `valve.steam.desktopgame.*` 2D game panels).
- **Games** — `UpdateGame` uses `screens/app_activity.h`: `VrScene` (`GetCurrentSceneProcessId`), or `FlatGamePresentation` (visible `valve.steam.desktopgame[.N]`, or a latched key while the dashboard stays closed after Steam's Enter gamepad mode / `hideDashboard`). Display hide and OutsideGames lasers share that activity. Leftover hidden `desktopgame` keys do not arm the latch. With In games = hide (default), Always mode becomes Dashboard. Chrome keep-alive also requires `ModeVisible()`.
- **Hand cutouts** — optional (`hands/`, `ft-handsctl`). `UpdateCutouts` composites side-by-side transparent hand capsules for real screens only (`!s.floating`). Tracking off or missing mmap = no cutouts. Pointer gestures are not wired.
- **Keyboard / instruments** — see [SCREENS_KEYBOARD.md](SCREENS_KEYBOARD.md); instruments share the same visibility rules.

## Related

[FT_FLOATD.md](FT_FLOATD.md), [SCREENS_TEST_HEADLESS.md](SCREENS_TEST_HEADLESS.md), `docs/floating-windows.md`, `docs/reference.md`.

## Tests

```
python3 test/test_app_activity.py
python3 test/test_overlay_budget_and_games.py
python3 test/test_screen_conceal.py
python3 test/test_float_phase3.py
python3 test/test_gaze_attention_order.py
python3 test/test_gaze_pointer_removed.py
python3 test/test_chrome_layout.py
python3 test/test_toolbar_reface_on_show.py
```
