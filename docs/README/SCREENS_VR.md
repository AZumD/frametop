# SCREENS_VR

Module: `screens/vr.cpp` / `screens/vr.h` (built into `ft-screens` by `screens/build.sh`)

## Purpose

OpenVR side of Frametop: virtual screen and floating-window panels, chrome, Spatial Instruments, visibility modes, and SteamVR game detection. DMA-BUF frames become overlay textures; lasers and the 3D mouse hit those overlays and map into KWin seats.

## Wiring

- **Screens** — `frametop.screen.N` plus under-chrome (bar, curve, roll, resize, anchor, profile slots).
- **Floating windows** — spare outputs create only `frametop.float.N` at start. Bar / dock / close / resize chrome is created in `EnsureFloatChrome` on the first `float` command and destroyed in `ReleaseFloatChrome` on `unfloat`, so idle float slots do not exhaust SteamVR’s overlay limit (which also blocks `valve.steam.desktopgame.*` 2D game panels).
- **Games** — `UpdateGame` hides displays for a scene app (`GetCurrentSceneProcessId`) **or** a **visible** `valve.steam.desktopgame[.N]` flatscreen panel. Controller lasers (`outside_games`) still follow scene apps only (`g_sceneApp`): a leftover hidden `desktopgame` key must not steal Frametop lasers. With In games = hide (default), Always mode becomes Dashboard so Frametop displays and instruments stay out of the way. Chrome keep-alive also requires `ModeVisible()` so it cannot revive panels during a game.
- **Hand cutouts** — optional (`hands/`, `ft-handsctl`). `UpdateCutouts` composites side-by-side transparent hand capsules for real screens only (`!s.floating`). Tracking off or missing mmap = no cutouts. Pointer gestures are not wired.
- **Keyboard / instruments** — see [SCREENS_KEYBOARD.md](SCREENS_KEYBOARD.md); instruments share the same visibility rules.

## Related

[FT_FLOATD.md](FT_FLOATD.md), [SCREENS_TEST_HEADLESS.md](SCREENS_TEST_HEADLESS.md), `docs/floating-windows.md`, `docs/reference.md`.

## Tests

```
python3 test/test_overlay_budget_and_games.py
python3 test/test_screen_conceal.py
python3 test/test_float_phase3.py
```
