# FT_DESKTOP

Module: `layout/ft_desktop.py`

## Purpose

FreeDesktop helpers shared by `ft-layout` / Display Settings and `session/ft-launch.py`: list `.desktop` apps, resolve icons (including SVG→PNG), and launch into nested Frametop Plasma.

## Notes

- `resolve_icon_path(..., allow_svg=True)` finds theme SVGs when no PNG exists; `ensure_raster_icon` / `convert_svg_to_png` rasterize via `rsvg-convert`, `magick`, or `convert`.
- `nested_launch_env()` loads `plasmashell.env` and refuses absolute / non-`wayland-*` `WAYLAND_DISPLAY` (outer ft-screens).
- `launch_desktop_id` uses `Exec=` under that nested env (not Gio activation), so windows land on existing Frametop displays.

## Tests

```
python3 test/test_launcher_instrument.py
```
