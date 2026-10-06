# REVIVE-DESKTOP

Script: `scripts/revive-desktop.sh`  
Also: `desktops.sh revive`

## Purpose

**One** path to bring the nested Frametop desktop back after a VR/flat game or a SteamVR bounce — stale `ft-screens` sockets, torn-down `…/frametop` runtime, missing plasmashell, or a silent start failure.

Does **not** restart SteamVR, gamescope, or steam. For SteamVR itself use [RECOVER-VR.md](RECOVER-VR.md).

## Behaviour

1. Require healthy SteamVR (`steamvr.service` + `vrserver` + `vrcompositor`); else exit 1 and point at `recover-vr.sh`
2. Require `screens/build/ft-screens` to contain `--spares`; else exit 2 and point at rebuild / `_fix_desktop_spares_mismatch.sh`
3. Report health (procs, socket, `plasmashell.env`, `@ft_screens` state, toolbar)
4. If already healthy: ensure `ft-taskbar` + `toolbar enable`, exit 0
5. Else: `desktops.sh stop`, clear stale sockets / orphaned `frametop` runtime, `start-desktop-on-frame.sh`, re-check

## Usage

```
scripts/revive-desktop.sh              # on the Frame, or from a PC (SSH)
scripts/revive-desktop.sh --check      # report only
scripts/revive-desktop.sh --force      # revive even if health looks ok
desktops.sh revive                     # syncs from a PC, then revive
desktops.sh revive --check
```

Older helpers `_fix_desktop_after_steamvr.sh` and `_check_desktop_spares_health.sh` call this script.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Healthy or revive succeeded |
| 1 | SteamVR unhealthy |
| 2 | `ft-screens` missing `--spares` |
| 3 | Still unhealthy after revive / `--check` |

## Tests

```
bash test/test_revive_desktop.sh
```

Also covered by `bash test/run-unit.sh`.

## Related

[START-DESKTOP-ON-FRAME.md](START-DESKTOP-ON-FRAME.md), [RECOVER-VR.md](RECOVER-VR.md), [_FIX_DESKTOP_SPARES_MISMATCH.md](_FIX_DESKTOP_SPARES_MISMATCH.md), [DESKTOP_TOOLBAR.md](DESKTOP_TOOLBAR.md)
