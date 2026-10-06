# RECOVER-VR

Script: `scripts/recover-vr.sh`

## Purpose

Recover a working SteamVR / headset boot after Frametop’s optional VR pieces (or a stuck SteamVR path file) misbehave. Safe over SSH. Does **not** reboot, does **not** restart SteamVR by itself, and does **not** delete layout profiles or other `~/.config/frametop*` data.

## Usage

```
scripts/recover-vr.sh           # prompts before each class of change
scripts/recover-vr.sh --yes     # apply every recovery step
```

## What it does

- Stop and disable `frametop-pointer.service` and `frametop-input-relay.service`
- Clean the input-relay fd store if present
- Unregister `ft_pointer` via `vrpathreg` (backs up `openvrpaths.vrpath` first)
- Set `POINTER=0` in `~/.config/frametop.conf`
- Remove an **empty** `~/.config/openvr/steamvr-pending.path` if present
- Stop a `steamvr.service` crash loop (so `steamvr-health-check` stops calling `displays_turn_off_drm_master`)

## Empty `steamvr-pending.path` (black screen after boot logo)

SteamOS’s `/usr/bin/steamvr` reads a pending runtime path from
`~/.config/openvr/steamvr-pending.path`. If that file exists but is **zero bytes**,
`realpath ""` fails under `set -e`, `steamvr path` prints nothing useful, and
`select_steamvr.sh` never launches `vrstartup`. `steamvr.service` then crash-loops;
`steamvr-health-check` resets `~/.local/share/Steam` and `displays_turn_off_drm_master`
turns the panels off — which looks like a black screen right after the boot logo.

Removing the empty pending file restores `steamvr path` → `/opt/steamvr`. You still need
to start or reboot into SteamVR yourself after recovery.

## Frametop desktop restart vs SteamVR

`desktops.sh stop` must **SIGTERM `ft-screens` before** stopping `frametop-desktop.service`, so OpenVR can `VR_Shutdown()` cleanly. Killing the unit first (or SIGKILL) can leave dangling overlays; XRService has then crashed into `HmdNotFound`, after which health-check turns the panels off. `desktops.sh start` refuses to launch unless `steamvr.service` is active and `vrserver` + `vrcompositor` are running.

When SteamVR is fine but the **nested desktop** will not come back after a game or a SteamVR bounce, use [REVIVE-DESKTOP.md](REVIVE-DESKTOP.md) (`desktops.sh revive`) — not this script.

## After recovery

```
# Put the headset on (panels need to come back), then:
systemctl --user start steamvr.service
# when vrcompositor is up:
desktops.sh start
```

Re-enable the optional 3D mouse later with:

```
pointer/driver/install.sh install && pointer/helper/run.sh install
desktops.sh relay install   # only if you also want the input relay again
```

## Tests

```
bash test/test_boot_safety.sh
bash test/test_steamvr_pending_path.sh
bash test/test_desktops_steamvr_safety.sh
```
