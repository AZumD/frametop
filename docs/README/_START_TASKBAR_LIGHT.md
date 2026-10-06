# _start_taskbar_light.sh

Restores the spatial taskbar on the Frame without a full SteamVR restart: syncs the
toolbar branch, restarts the nested desktop only if `ft-screens` does not accept
`toolbar state`, starts **`ft-taskbar`**, and runs **`ft-layout toolbar enable`**.

## Usage

```
bash test/_start_taskbar_light.sh
```

Requires `frametop-stage1-chrome` (`stage2-desktop-toolbar`) as the sync source (see
`ROOT` at the top of the script).

## When to use

After rebuilding `ft-screens` while the desktop stayed up: the old process keeps the
previous binary in memory (`/proc/.../exe (deleted)`), so toolbar socket commands
fail and the bar never appears even though `build/ft-screens` on disk is new.

For a missing checkout (no `ft-taskbar.py` on the Frame), use
`frametop-stage1-chrome/test/_restore_spatial_toolbar.sh` instead.
