# INPUT-RELAY

Script / module: `input/input-relay.py` (user service `frametop-input-relay.service`)

## Purpose

Stable virtual mouse/keyboard for SteamVR, device role rules, volume-key takeover, pointer/controller actions, and typing into ft-screens.

## Control hardening

The abstract control socket `@frametop_relay` has no permissions. Each received datagram is dispatched inside a try/except so a malformed command (for example `watch abc`) is logged and ignored instead of killing the process. A dead relay would drop every grab, including the volume keys that keep gamescope from aborting.

## Stuck-key reconciliation

Keys sent to ft-screens as `key CODE 1` are tracked in `screens_down`. About once a second the relay compares that set to the kernel key state (`EVIOCGKEY`) on every open node and sends `key CODE 0` for anything the desktop still believes is down that no physical device holds. On startup it also releases Meta/Ctrl/Alt/Shift on the desktop in case a previous relay left them stuck.

## Tests

```
python3 test/test_input_relay_control.py   # needs Linux/WSL abstract AF_UNIX
bash test/test_boot_safety.sh
bash test/test_steamvr_client_init.sh
```

## Related

See `docs/design.md` (Input relay) and `docs/reference.md` (Input relay).
