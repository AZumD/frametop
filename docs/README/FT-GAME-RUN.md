# FT-GAME-RUN

Script: `session/ft-game-run` (+ `session/ft_game_run.py`)

Conceptual name: **tovakai-game-run**. Process/script name `ft-game-run` (≤15 chars).

## Purpose

Steam-owned launch wrapper: load Frametop nested Plasma display env from
`$HOST_RUNTIME/frametop/plasmashell.env`, override only display/session variables,
then `exec` Steam’s unchanged command (`%command%`).

Steam still chooses Proton, runtime, tracking, Steam Input, Stop Game, etc.

## Overrides (from plasmashell.env)

- `DISPLAY`
- `WAYLAND_DISPLAY`
- `XDG_RUNTIME_DIR`
- `XDG_SESSION_TYPE`
- `XAUTHORITY` (when present)

Does **not** override `DBUS_SESSION_BUS_ADDRESS` (Steam IPC / overlay stay on the
host/pressure-vessel bus).

## Steam launch options (probe)

```
/home/steamos/dev/frametop/session/ft-game-run %command%
```

Helpers preserve existing user options around `%command%` (`wrap_launch_options`).

## Log

`/tmp/frametop-game-run.log`

## Tests

```
python3 test/test_ft_game_run.py
```

Live Stage 3 probes: [STEAM_GAME_ROUTING.md](STEAM_GAME_ROUTING.md),
`test/_arm_game_routing_phase5.sh`, `_verify_game_routing_phase5.sh`,
`_restore_game_launch_options.sh`.
