# FT_LAYOUT

Script / module: `layout/ft_layout.py` (CLI `layout/ft-layout`)

## Purpose

Arrange Frametop virtual screens, push visibility / follow / Spatial Instruments to `ft-screens`, and apply KWin output scales so the VR pointer matches Display Settings scale.

## Apply resilience

`ft-layout apply` (and the desktop startup `--wait` path) must keep working when SteamVR has not yet published an HMD pose:

1. **Visibility first** — `except_dashboard` and related settings are sent before place, so dashboards hide desktop even if arrange is deferred.
2. **Head pose retries** — `read_head_pose` retries; if still missing, screens/instruments place from a fallback eye `(0, 1.5, 0)` and yaw `0` (re-run `apply` once tracking is up for a correct origin).
3. **Scales after apply** — KWin scales + `scale N` to ft-screens still run when arrange raises, so pointer seat mapping stays correct at fractional scales (e.g. 1.25).
4. **Instruments** — pushed from layout even without head pose; overlay keys left after a hard kill are reclaimed in `screens/vr.cpp` (`CreateOrRecycleOverlay`).

## Desktop toolbar

`ft-layout apply` also restores the spatial toolbar (`ft_toolbar` / `toolbar …` on `@ft_screens`) and any docked screens. The toolbar is **enabled by default** (0.1.0). CLI: `ft-layout toolbar state|enable|disable|…` and `ft-layout dock N on|off|…` — see [DESKTOP_TOOLBAR.md](DESKTOP_TOOLBAR.md).

## Usage

```
layout/ft-layout apply [--wait SEC] [--duration MS]
layout/ft-layout scale
layout/ft-layout instrument list|enable|…
layout/ft-layout toolbar state|enable|disable|…
layout/ft-layout dock N on|off|toggle|state
```

## Hiding one screen at a time

```
layout/ft-layout hide N|all     # hidden on its own, whatever the visibility mode or hotkey say
layout/ft-layout show N|all
layout/ft-layout hidden         # the screens hidden on their own (1-based, space separated)
```

The flag is `"hidden": true` on the screen's entry in `~/.config/frametop-layout.json`
(absent when shown). Named Spatial Profiles carry it via `PROFILE_SCREEN_KEYS`.
`set_hidden` saves it and, if the desktop runs, sends `conceal N` / `reveal N` to
ft-screens. `send_hidden` pushes the whole set; it runs at the end of `apply_screens`
(after the screens are placed or transitioned) and on the `apply --wait` startup paths.
An ft-screens from before `conceal` is logged and skipped. Windows stay on a hidden
screen's KWin output; only the VR overlay is suppressed (`alone` in ft-screens). Spatial
Instruments are unaffected. The CLI uses hide/show; the wire protocol uses
conceal/reveal/concealed so it never collides with the global `hide` command.

## Tests

```
python3 test/test_apply_without_head.py
python3 test/test_pointer_coords.py
python3 test/test_instrument_visibility.py
python3 test/test_spatial_instruments.py
python3 test/test_desktop_toolbar.py
python3 test/test_toolbar_dock.py
```
