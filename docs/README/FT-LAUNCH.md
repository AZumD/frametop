# FT-LAUNCH

Script: `session/ft-launch.py`

## Purpose

Abstract datagram bridge `@frametop_launch` so Launcher Spatial Instruments (running inside distrobox `ft-screens`) can start apps inside the nested Frametop Plasma session.

## Commands

```
desktop <desktop-id>       # Application .desktop
action <semantic>          # ft-layout action …
command <json-argv>        # detached argv (no shell)
shell <text>               # /bin/sh -c …
ping
```

## Notes

- Started by `frametop-session.sh` inside `dbus-run-session` **before** Plasma, so the process’s own `WAYLAND_DISPLAY` is still the outer ft-screens socket.
- Each activation reloads `$XDG_RUNTIME_DIR/plasmashell.env` (from `ft-shell-watch`) and launches with nested `wayland-N`. Using the outer display would open apps as extra host-compositor overlays (floating VR panels Plasma cannot close).
- Does not `eval` plasmashell.env; parses NUL records via `ft_desktop.nested_launch_env`.
- Log: `/tmp/frametop-launch.log`. Process name `ft-launch` (≤15 chars).

## Tests

```
python3 test/test_launcher_instrument.py
```
