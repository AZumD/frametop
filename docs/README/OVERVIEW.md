# OVERVIEW

Frametop tools and docs for the Steam Frame nested desktop.

## Scripts / modules

| Path | Doc |
|------|-----|
| `scripts/frame-background` | [FRAME-BACKGROUND.md](FRAME-BACKGROUND.md) |
| `scripts/openvr_settings.py` | [OPENVR_SETTINGS.md](OPENVR_SETTINGS.md) |
| `scripts/make-equirect-test.py` | [MAKE-EQUIRECT-TEST.md](MAKE-EQUIRECT-TEST.md) |
| `scripts/recover-vr.sh` | [RECOVER-VR.md](RECOVER-VR.md) |
| `scripts/rebuild-screens-on-frame.sh` | [REBUILD-SCREENS-ON-FRAME.md](REBUILD-SCREENS-ON-FRAME.md) |
| `scripts/start-desktop-on-frame.sh` | [START-DESKTOP-ON-FRAME.md](START-DESKTOP-ON-FRAME.md) |
| `display-settings/ft_display_settings.py` | [FT_DISPLAY_SETTINGS.md](FT_DISPLAY_SETTINGS.md) |
| `layout/ft_layout.py` | [FT_LAYOUT.md](FT_LAYOUT.md) |
| `session/ft-launch.py` | [FT-LAUNCH.md](FT-LAUNCH.md) |
| `layout/ft_desktop.py` | [FT_DESKTOP.md](FT_DESKTOP.md) |
| `input/ft-textinput` | [FT_TEXTINPUT.md](FT_TEXTINPUT.md) |
| `screens/keyboard.cpp` | [SCREENS_KEYBOARD.md](SCREENS_KEYBOARD.md) |

Layout / Spatial Instruments CLI and profile format live in `docs/reference.md` (and `docs/design.md`). `ft-layout apply` still pushes visibility, KWin scales, and instruments when the HMD pose is not ready yet (see [FT_LAYOUT.md](FT_LAYOUT.md)). Display Settings → **Background** uses `frame-background`; recover-vr also clears a broken empty `steamvr-pending.path` that can black-screen SteamVR after the boot logo.
