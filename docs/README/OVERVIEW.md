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
| `session/ft-launch.py` | [FT-LAUNCH.md](FT-LAUNCH.md) |
| `layout/ft_desktop.py` | [FT_DESKTOP.md](FT_DESKTOP.md) |

Layout / Spatial Instruments CLI and profile format live in `docs/reference.md` (and `docs/design.md`). Display Settings → **Background** uses `frame-background`; recover-vr also clears a broken empty `steamvr-pending.path` that can black-screen SteamVR after the boot logo.
