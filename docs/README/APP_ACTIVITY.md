# APP_ACTIVITY

Header: `screens/app_activity.h`  
Harness: `test/app_activity_harness.cpp`  
Tests: `test/test_app_activity.py`

## Purpose

Pure ownership state for SteamVR presentation/input: `Desktop`, `VrScene`, or
`FlatGamePresentation`. `screens/vr.cpp` uses it so display hide and OutsideGames
laser flags share one decision (not separate `GetCurrentSceneProcessId` vs leftover
`desktopgame` guesses).

## Notes

- Arms a latch when `valve.steam.desktopgame[.N]` is visible.
- Holds `FlatGamePresentation` while that key stays registered and the dashboard is
  closed — Steam's "Enter gamepad mode" calls `hideDashboard` and often hides the
  theater overlay; without the latch Frametop would reappear and steal controllers.
- Releases after six samples (~3 s) of dashboard open without a visible theater (or when the
  overlay key is gone). Leftover hidden keys never arm the latch by themselves.
- OutsideGames lasers: blocked for `VrScene`, and for `FlatGamePresentation` only while
  the dashboard is closed (gamepad mode). Theater + open dashboard still allows lasers.
- Does not inspect Steam game processes.

## Tests

```
python3 test/test_app_activity.py
```
