# HANDS

Module: `hands/` (CLI: `hands/run.sh`, `hands/ft-handsctl`; binaries `ft-camd`, `ft-hands`)

## Purpose

Optional, experimental hand tracking for the Steam Frame. Camera capture (`ft-camd`) and tracker (`ft-hands`) publish shared hand state under `/run/user/UID/frametop-hands/`. Frametop can draw **hand cutouts** through real desktop screens (`screens/handcut.cpp`) so passthrough hands show through panels. Hands do **not** drive the pointer in this phase (no pinch click / grip drag).

## Opt-in

- Not part of `./install.sh`.
- Install once: `hands/run.sh install` (builds, `setcap` for ft-camd, installs **disabled** user units).
- Runtime: `ft-handsctl on` / `off` / `status` / `log` / `cutouts on|off|state` / `gestures` (diagnostics only).
- Services stop with SteamVR (`PartOf=steamvr.service`) and do not auto-start with the desktop.

## Wiring

- `hands/camd/` — borrows XRService DMA-BUFs; ring `cam-ring`.
- `hands/track/` — ncnn palm/hand models → `hands` + `gestures` mmap files.
- `hands/include/fh_hands.h`, `fh_gestures.h` — shared formats (gesture fields reserved for Phase 3D).
- `screens/handcut.cpp` — cutouts for **non-floating** screens only (`!s.floating`); floats use texture crops incompatible with side-by-side cutout buffers.
- Control: `@ft_screens` commands `cutouts on|off|state|predict …|lead …`.

## Related

[SCREENS_VR.md](SCREENS_VR.md), `hands/README.md`, `docs/reference.md`.

## Tests

```
python3 test/test_hands_phase3c.py
python3 test/test_float_cross_panel_dnd.py
```
