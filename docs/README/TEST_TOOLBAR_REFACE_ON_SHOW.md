# TEST_TOOLBAR_REFACE_ON_SHOW

Script: `test/test_toolbar_reface_on_show.py`

## Purpose

Source-level guards for the “taskbar icons go invisible” regression and the screen-chrome dock/slot cleanups.

## Covers

- `ShowToolbar(true)` calls `RefaceToolbarBtn` on every cell (dashboard yield / Hide-Show must re-upload faces)
- `LightToolbarBtn` resets `SetOverlayMouseScale` after `SetOverlayRaw`
- `MakePanel` destroys leftover `*.slotN` overlays and never creates digit slot chrome
- `PlaceChrome` always sizes `dockButton` to grip (not only when floating)

## Run

```
python3 test/test_toolbar_reface_on_show.py
```
