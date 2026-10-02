# SCREENS_KEYBOARD

Module: `screens/keyboard.cpp` / `screens/keyboard.h` (built into `ft-screens` by `screens/build.sh`)

## Purpose

Frametop's keyboard: a panel of keys (a US laptop layout, Esc where Caps Lock would be, arrows, a Close key) that ft-screens shows for a text field on the desktop. Any controller laser or the 3D mouse types on it. Keys go out as Linux key codes (`FT_KEY` events) to the focused screen's seat, so every app takes them; Shift, Ctrl and Alt latch and a held key repeats. The grab bar along the top moves it. Labels are drawn on the CPU with stb_truetype into shared DMA-BUFs (no flicker).

## Wiring

- `screens/vr.cpp`: `ft_vr_keyboard_show(screen)` places it 0.7 m ahead of the head (level) and 0.35 m below the eyes, facing the eyes; with no head pose it doesn't open. `ft_vr_keyboard_hide()` closes it. `ft_vr_poll` forwards `keyboard::Poll` events as `FT_KEY` / `FT_KEYBOARD_CLOSED`, hides it when the screens hide, and every 9 ticks steps it aside while the Steam menu or Steam's own keyboard (`valve.steam.gamepadui.keyboard`) is up, bringing it back where it was afterwards.
- `screens/compositor.c`: control command `vrkeyboard show|hide|toggle|close`. It opens for the screen KWin has keyboard focus on; `hide` closes only a keyboard a text field opened, after about a third of a second; `close` (from `ft-layout apply`) closes it however it opened.
- `screens/build.sh`: compiles `keyboard.cpp`, fetches `stb_truetype.h` (pinned), links gbm.
- `pointer/helper/ft-pointer.cpp`: every `frametop.*` overlay counts as a real panel (the keyboard's shared texture reports 0x0).

## Related

[FT_TEXTINPUT.md](FT_TEXTINPUT.md), [INPUT-RELAY.md](INPUT-RELAY.md), [FT_LAYOUT.md](FT_LAYOUT.md); `docs/reference.md` and `docs/design.md`.

## Tests

```
python3 test/test_vr_keyboard_relay.py
python3 test/test_screen_conceal.py        # source wiring of vr.cpp
bash test/test_steamvr_client_init.sh
```

The C/C++ needs the Frame's dev container to build (`screens/build.sh`); the tests above don't compile it.
