# SCREENS_TEST_HEADLESS

Script: `screens/test/headless.sh` (helper: `screens/test/observe.js`)

## Purpose

Throwaway nested desktop for experiments and automated checks **beside** the live Frametop session. Starts `ft-screens --no-vr` with its own Wayland socket, control socket `@ft_screens_test`, runtime dir, D-Bus, and a bare nested KWin. Does not touch SteamVR, the input relay, or the production `@ft_screens` socket.

## Prerequisites

Build ft-screens first (`screens/build.sh` on the Frame / in the `dev` container). Run on the Frame (or from the PC via `scripts/sync.sh` + `on_frame`).

## Usage

```
screens/test/headless.sh start [SCREENS] [SPARES]
screens/test/headless.sh ask 'toplevels'
screens/test/headless.sh ask 'input 1 move 100 100'
screens/test/headless.sh run kate
screens/test/headless.sh stop
```

## Related flags in ft-screens

- `--no-vr` — skip OpenVR / overlays / relay contact
- `--control NAME` — abstract control socket (default `ft_screens`; tests use `ft_screens_test`)
- `--socket NAME` — Wayland socket under `$XDG_RUNTIME_DIR`

## Tests

```
bash test/test_steamvr_client_init.sh   # static: --no-vr / ft_screens_test present
# On the Frame, after screens/build.sh:
#   screens/test/headless.sh start
#   screens/test/headless.sh ask toplevels
#   screens/test/headless.sh stop
```
