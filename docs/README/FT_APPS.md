# FT_APPS

Module: `float/ft_apps.py` (CLI: `float/ft-float-apps`)

## Purpose

“Launch as Standalone” for the Frametop desktop’s app menus. Writes copies of `.desktop` files under `~/.local/share/frametop/apps/applications` with an extra action that runs `ft-float launch <desktop id>`, so the app’s first window floats in VR instead of landing on a normal screen. The session puts that apps tree first in `XDG_DATA_DIRS` for nested Plasma only; Desktop Mode never sees the copies. Drops `DBusActivatable` on copies so D-Bus-activated apps do not try to run the unknown action themselves.

## Wiring

- `float/ft-floatd`: rewrites the copies when apps change; launches floating via `launch` / `run`.
- Session start: `ft-float-apps` runs before Plasma so menus already show the action.
- Overlay / panel side: same spare outputs and `frametop.float.*` panels as [FT_FLOATD.md](FT_FLOATD.md).

## Related

[FT_FLOATD.md](FT_FLOATD.md), [FT_DESKTOP.md](FT_DESKTOP.md), `docs/floating-windows.md`.

## Tests

```
python3 test/test_float_screens_wiring.py
# Manual on the Frame: Launch as Standalone from a nested Plasma app menu, confirm a float panel.
```
