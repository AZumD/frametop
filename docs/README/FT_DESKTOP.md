# FT_DESKTOP

Module: `layout/ft_desktop.py`

## Purpose

FreeDesktop helpers shared by `ft-layout` / Display Settings and `session/ft-launch.py`: list `.desktop` apps, resolve icons (including SVG→PNG), and launch into nested Frametop Plasma.

## Notes

- `resolve_icon_path(..., allow_svg=True)` finds theme SVGs when no PNG exists; `ensure_raster_icon` / `convert_svg_to_png` rasterize via `rsvg-convert`, `magick`, or `convert`.
- `nested_launch_env()` loads `plasmashell.env` and refuses absolute / non-`wayland-*` `WAYLAND_DISPLAY` (outer ft-screens).
- `launch_desktop_id` uses `Exec=` under that nested env (not Gio activation), so windows land on existing Frametop displays.
- `find_desktop_by_id` round-trips FreeDesktop ids from vendor subdirs (`kde/foo.desktop` ↔ `kde-foo.desktop`).
- Inside distrobox, `xdg_data_dirs()` also searches `/run/host/usr/share` so Display Settings lists host SteamOS apps.

PC sync targets `~/dev/frametop`. The Steam “Desktop” launcher and `ft-screens` must use that tree (`desktops.sh install`); an old `~/frametop` checkout keeps running a stale binary (soft-follow / overlay fixes never load).

## Tests

```
python3 test/test_launcher_instrument.py
```
