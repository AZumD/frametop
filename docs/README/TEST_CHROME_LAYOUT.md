# TEST_CHROME_LAYOUT

Script: `test/test_chrome_layout.py`

## Purpose

Mirrors `screens/vr.cpp` `ControlOffsets` / `DockButtonX` / `BarY` without OpenVR: the under-screen chrome strip is bar, curve, roll, resize, anchor, dock (and close for floats). Profile digit slots under screens are gone — the toolbar Displays popup owns profiles.

## Covers

- Control list has no `slotN` / keyboard entries
- Dock sits to the right of roll; float adds close after dock
- Dock width contract equals grip (guards the gigantic dock overlay bug)

## Run

```
python3 test/test_chrome_layout.py
```
