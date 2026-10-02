# FT_POINTER

Script / module: `pointer/helper/ft-pointer.cpp` (user service via `pointer/helper/run.sh`)

## Purpose

3D pointer helper for SteamVR overlays: laser hit-testing, drag lock, SteamVR Settings workaround, `POINTER_IGNORE`, and placement helpers used by layout.

## Floating panels

`FramePanel()` treats `frametop.screen.N`, `frametop.float.N`, and `frametop.float.N.sub.K` as desktop panels the laser can retarget across while a press is held and the pressed overlay has not moved. Left release sends `up` to `@ft_screens` as a backstop for the catcher. `POINTER_IGNORE` still cannot drop any `frametop.*` key (Phase 2 hard guard).

Cross-panel DnD also needs ft-screens to hand KWin pointer focus to the destination on enter (`x+1` then motion) without `clear_focus` first (that cancels the drag); see [FT_FLOATD.md](FT_FLOATD.md). Soft-follow must not clear the helper's `pressKey` (carry threshold is ~5 cm of panel origin motion). Set `FT_DND_DEBUG=1` on ft-screens for transition logs (`dnd press|retarget|leave-suppressed|…`).

## Related

[FT_FLOATD.md](FT_FLOATD.md), [INPUT-RELAY.md](INPUT-RELAY.md), `docs/floating-windows.md`.

## Tests

```
python3 test/test_pointer_ignore.py
python3 test/test_float_phase3.py
python3 test/test_float_cross_panel_dnd.py
bash test/test_steamvr_client_init.sh
```
