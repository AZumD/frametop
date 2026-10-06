# _restore_taskbar_rock_solid.sh

Rebuild `ft-screens` with the spatial DesktopToolbar, restart the nested desktop,
enable the toolbar via `ft-layout toolbar enable`, and gate on:

- `toolbar state` → `ok …` on `@ft_screens`
- `ft-taskbar` process running

## Usage

```
bash test/_restore_taskbar_rock_solid.sh
```

Does **not** restart SteamVR/gamescope.

## Why

Syncing a tree without the toolbar (or rebuilding without `desktop_toolbar.inc` /
`steamvr_assets`) leaves a desktop that starts but has no taskbar. Session start
must always launch `ft-taskbar`, and `scripts/start-desktop-on-frame.sh` now
force-enables the toolbar after start.
