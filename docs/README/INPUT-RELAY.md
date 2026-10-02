# INPUT-RELAY

Script / module: `input/input-relay.py` (user service `frametop-input-relay.service`)

## Purpose

Stable virtual mouse/keyboard for SteamVR, device role rules, volume-key takeover, pointer/controller actions, and typing into ft-screens.

## Control hardening

The abstract control socket `@frametop_relay` has no permissions. Each received datagram is dispatched inside a try/except so a malformed command (for example `watch abc`) is logged and ignored instead of killing the process. A dead relay would drop every grab, including the volume keys that keep gamescope from aborting.

## Stuck-key reconciliation

Keys sent to ft-screens as `key CODE 1` are tracked in `screens_down`. About once a second the relay compares that set to the kernel key state (`EVIOCGKEY`) on every open node and sends `key CODE 0` for anything the desktop still believes is down that no physical device holds. On startup it also releases Meta/Ctrl/Alt/Shift on the desktop in case a previous relay left them stuck.

## Frametop's keyboard

The desktop's input method ([FT_TEXTINPUT.md](FT_TEXTINPUT.md)) sends `textfield 1|0` to `@frametop_relay` when a text field gains or loses keyboard focus. The relay turns that into `vrkeyboard show|hide|toggle` datagrams for ft-screens, depending on the rules file (`~/.config/frametop-input.json`):

| Key | Values | Meaning |
|-----|--------|---------|
| `vr_keyboard` | `always` | every text field opens it |
| | `no_keyboard` (default, also for an unknown value) | only while no pass-through keyboard is connected |
| | `button` | only the `keyboard_toggle` action opens it |
| | `never` | never, and `keyboard_toggle` does nothing either |
| `vr_keyboard_persist` | `true` (default) / `false` | `false`: losing focus sends `vrkeyboard hide` (ft-screens only closes a keyboard a text field opened) |

`keyboard_toggle` ("Open/close keyboard") is a new action, before `key` in `ACTIONS`, for mouse buttons and Frame controller buttons. Both paths go through `do_action`, which sends `vrkeyboard toggle` on a press (unless the mode is `never`) and hands every other action to `Pointer.action`. A keyboard made by a program through uinput (frame-voice's, say) doesn't count as "connected": `probe` marks a node `uinput` when its sysfs path is under `/sys/devices/virtual/input/`, `Node.describe()` reports it, and the `no_keyboard` check skips it (as it does keyboards set to Ignore or Pointer).

## Floating windows

`float_toggle` and `dock_all` send `float pointer` / `dock all` to ft-floatd on `@frametop_float` (they work even when pointer mode is off). A rules file without `key_bindings` gets `DEFAULT_KEY_BINDINGS`: Meta+Shift+F (`42+125+33`) → `float_toggle`. A file that defines its own `key_bindings` object, even `{}`, does not get that default. Combinations are taken on passthrough keyboards before the key is typed; Meta is swallowed on the desktop for the combo so Plasma's launcher does not open. This fork does not ship gaze key bindings.

## Tests

```
python3 test/test_input_relay_control.py   # needs Linux/WSL abstract AF_UNIX
python3 test/test_vr_keyboard_relay.py     # modes, persist, uinput detection, keyboard_toggle
python3 test/test_float_phase3.py          # float wiring, Meta+Shift+F, crop math
bash test/test_boot_safety.sh
bash test/test_steamvr_client_init.sh
```

## Related

See `docs/design.md` (Input relay) and `docs/reference.md` (Input relay).
