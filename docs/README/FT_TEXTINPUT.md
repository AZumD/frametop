# FT_TEXTINPUT

Script: `input/ft-textinput` (started by KWin, not by a service)

## Purpose

Frametop's input method for the nested desktop. It only reports focus: when the focused app turns text input on or off for a field, it sends `textfield 1` or `textfield 0` to the input relay (`@frametop_relay`), which decides (Keyboard page of Frametop Input Settings) whether ft-screens opens its keyboard. Nothing typed passes through it; the keyboard's keys reach the focused screen as key presses from ft-screens.

## How it runs

`session/frametop-session.sh` shadows `kwin_wayland_wrapper` and adds `--inputmethod <repo>/input/ft-textinput`, so KWin starts the program and passes its Wayland connection in `WAYLAND_SOCKET`. It speaks the Wayland wire protocol itself (`zwp_input_method_v1` only), so it needs nothing but Python on the SteamOS host. It exits when KWin goes away; with no `WAYLAND_SOCKET` it exits with a message.

The gamescope session puts `QT_IM_MODULE=xim`, `GTK_IM_MODULE=xim` and `XMODIFIERS` in the systemd user environment. With those, Qt and GTK apps use X input methods and never turn on Wayland text input, so the session script unsets them (in the loop that drops the Steam client's runtime variables).

## Which apps report a text field

Qt, GTK and Firefox apps (Wayland text input). Chromium, Electron and X11 apps don't; for those, map **Open/close keyboard** (`keyboard_toggle`) to a mouse or controller button.

## Messages

| Datagram | To | When |
|----------|----|------|
| `textfield 1` | `@frametop_relay` | a text field gained keyboard focus |
| `textfield 0` | `@frametop_relay` | it lost focus |

If the relay isn't running the datagram is dropped.

## Related

[INPUT-RELAY.md](INPUT-RELAY.md) (what the relay does with it), [SCREENS_KEYBOARD.md](SCREENS_KEYBOARD.md) (the panel), `docs/design.md` (why an input method and why our own panel).

## Tests

```
python3 test/test_vr_keyboard_relay.py
bash test/test_steamvr_client_init.sh      # session script wiring (--inputmethod, IM variables)
```
