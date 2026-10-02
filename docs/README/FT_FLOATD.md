# FT_FLOATD

Module: `float/ft_floatd.py` (CLI: `float/ft-floatd`, `float/ft-float`; KWin script `float/frametop-float.js`)

## Purpose

Daemon for Frametop floating windows. Runs inside the nested Plasma session and owns which window sits on which spare KWin output / SteamVR panel. It loads the `frametop-float` KWin script, talks to `ft-screens` (`@ft_screens`) for spare size and panel crop (`float` / `unfloat` / `sub` / `pose`), and uses `kscreen-doctor` to enable, place, and size spare outputs. Commands arrive on `@frametop_float` from `ft-float`, the input relay, and ft-screens (dock / close / resize / scale).

## Wiring

- `screens/compositor.c`: `--spares N`, spare toplevels call `ft_vr_float_create` / `ft_vr_float_output`; Meta+scroll on a spare sends `scale` to `@frametop_float`.
- `screens/vr.cpp`: overlays `frametop.float.N` (+ `.bar` / `.dock` / `.close` / `.sub.K`); control commands `float`, `unfloat`, `pose`, `sub`, `minimized`, `carry`.
- `layout/ft_layout.py` `outputs()`: drops `WL-*` at and after the configured screen count so layout never rearranges spares.
- Session / Display Settings: `FLOAT_SLOTS`, `FLOAT_MARGIN` in `~/.config/frametop.conf` (see `docs/floating-windows.md`).

## Related

[FT_APPS.md](FT_APPS.md), [SCREENS_TEST_HEADLESS.md](SCREENS_TEST_HEADLESS.md), `docs/floating-windows.md`.

## Tests

```
python3 test/test_float_screens_wiring.py
python3 test/test_float_phase3.py
# On the Frame, after screens/build.sh:
#   screens/test/headless.sh start 2 3
#   screens/test/headless.sh floatd
#   screens/test/headless.sh float list
#   screens/test/headless.sh stop
```
