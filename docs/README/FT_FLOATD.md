# FT_FLOATD

Module: `float/ft_floatd.py` (CLI: `float/ft-floatd`, `float/ft-float`; KWin script `float/frametop-float.js`)

## Purpose

Daemon for Frametop floating windows. Runs inside the nested Plasma session and owns which window sits on which spare KWin output / SteamVR panel. It loads the `frametop-float` KWin script, talks to `ft-screens` (`@ft_screens`) for spare size and panel crop (`float` / `unfloat` / `sub` / `pose`), and uses `kscreen-doctor` to enable, place, and size spare outputs. Commands arrive on `@frametop_float` from `ft-float`, the input relay, and ft-screens (dock / close / resize / scale).

## Wiring

- `screens/compositor.c`: `--spares N`, spare toplevels call `ft_vr_float_create` / `ft_vr_float_output`; Meta+scroll on a spare sends `scale` to `@frametop_float`. Cross-panel drag/drop: on a focus change, enter is at `(x+1,y)` so the following motion at `(x,y)` is not dropped by wlroots (KWin nested otherwise keeps the old output's pointer). Do not `clear_focus` before that enter — it cancels an in-progress Wayland drag.
- `screens/vr.cpp`: overlays `frametop.float.N` (+ `.bar` / `.dock` / `.close` / `.sub.K` created lazily via `EnsureFloatChrome` when a window floats, released on `unfloat`); control commands `float`, `unfloat`, `pose`, `sub`, `minimized`, `carry`. FocusLeave while a button is held does not clear KWin pointer; the catcher covers gaps; `up` is the helper's release backstop. Idle float chrome is not kept alive so SteamVR's overlay budget stays free for flatscreen `desktopgame` panels. Cross-panel DnD: motion retargets `g_press.screen`; a button-up delivered to the press-time overlay is rewritten to that retarget so the drop is not stuck on the seat.
- `pointer/helper/ft-pointer.cpp`: `FramePanel()` + held-drag retarget across `frametop.screen.*` / `frametop.float.*` (not `.bar`), and `up` on left release. Soft-follow pose noise must not clear `pressKey` (only ~5 cm of origin motion counts as a carry).
- `layout/ft_layout.py` `outputs()`: drops `WL-*` at and after the configured screen count so layout never rearranges spares.
- Session / Display Settings: `FLOAT_SLOTS`, `FLOAT_MARGIN` in `~/.config/frametop.conf` (see `docs/floating-windows.md`).
- Debug: `FT_DND_DEBUG=1` on ft-screens logs `dnd press|retarget|leave-suppressed|release-away` transitions.

## Related

[FT_APPS.md](FT_APPS.md), [SCREENS_TEST_HEADLESS.md](SCREENS_TEST_HEADLESS.md), `docs/floating-windows.md`.

## Tests

```
python3 test/test_float_screens_wiring.py
python3 test/test_float_phase3.py
python3 test/test_float_cross_panel_dnd.py
python3 test/test_overlay_budget_and_games.py
# On the Frame, after screens/build.sh:
#   screens/test/headless.sh start 2 3
#   screens/test/headless.sh floatd
#   screens/test/headless.sh float list
#   screens/test/headless.sh stop
```
