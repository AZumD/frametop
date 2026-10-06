# START-DESKTOP-ON-FRAME

Script: `scripts/start-desktop-on-frame.sh`

## Purpose

Start the Frametop desktop on the Steam Frame host with a SteamVR health gate. Used by `desktops.sh start` so the start path is not an inline SSH string (those have broken under PC/WSL quoting).

## Behaviour

1. Require `steamvr.service` active and both `vrserver` and `vrcompositor` running
2. No-op if Frametop is already running
3. `systemd-run --user --unit frametop-desktop` → `session/frametop-session.sh`
4. After start: if `toolbar state` works, ensure `ft-taskbar` is running and run
   `ft-layout toolbar enable` so the spatial taskbar is visible

## Usage

```
scripts/start-desktop-on-frame.sh          # on the Frame
desktops.sh start                          # from a PC (syncs, then runs this on the Frame)
desktops.sh revive                         # after a game / SteamVR bounce (see REVIVE-DESKTOP.md)
```

## Tests

```
bash test/test_desktops_steamvr_safety.sh
```
