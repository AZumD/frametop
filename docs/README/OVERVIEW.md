# OVERVIEW

Frametop tools and docs for the Steam Frame nested desktop.

## Scripts / modules

| Path | Doc |
|------|-----|
| `scripts/frame-background` | [FRAME-BACKGROUND.md](FRAME-BACKGROUND.md) |
| `scripts/_env.sh` | [SCRIPTS_ENV.md](SCRIPTS_ENV.md) |
| `scripts/openvr_settings.py` | [OPENVR_SETTINGS.md](OPENVR_SETTINGS.md) |
| `scripts/make-equirect-test.py` | [MAKE-EQUIRECT-TEST.md](MAKE-EQUIRECT-TEST.md) |
| `scripts/recover-vr.sh` | [RECOVER-VR.md](RECOVER-VR.md) |
| `scripts/rebuild-screens-on-frame.sh` | [REBUILD-SCREENS-ON-FRAME.md](REBUILD-SCREENS-ON-FRAME.md) |
| `scripts/start-desktop-on-frame.sh` | [START-DESKTOP-ON-FRAME.md](START-DESKTOP-ON-FRAME.md) |
| `display-settings/ft_display_settings.py` | [FT_DISPLAY_SETTINGS.md](FT_DISPLAY_SETTINGS.md) |
| `layout/ft_layout.py` | [FT_LAYOUT.md](FT_LAYOUT.md) |
| `session/ft-launch.py` | [FT-LAUNCH.md](FT-LAUNCH.md) |
| `layout/ft_desktop.py` | [FT_DESKTOP.md](FT_DESKTOP.md) |
| `input/input-relay.py` | [INPUT-RELAY.md](INPUT-RELAY.md) |
| `input/ft-textinput` | [FT_TEXTINPUT.md](FT_TEXTINPUT.md) |
| `pointer/helper/ft-pointer.cpp` | [FT_POINTER.md](FT_POINTER.md) |
| `screens/keyboard.cpp` | [SCREENS_KEYBOARD.md](SCREENS_KEYBOARD.md) |
| `screens/vr.cpp` | [SCREENS_VR.md](SCREENS_VR.md) |
| `screens/test/headless.sh` | [SCREENS_TEST_HEADLESS.md](SCREENS_TEST_HEADLESS.md) |
| `float/ft_floatd.py` | [FT_FLOATD.md](FT_FLOATD.md) |
| `float/ft_apps.py` | [FT_APPS.md](FT_APPS.md) |
| `hands/` | [HANDS.md](HANDS.md) |

Layout / Spatial Instruments CLI and profile format live in `docs/reference.md` (and `docs/design.md`). `ft-layout apply` still pushes visibility, KWin scales, and instruments when the HMD pose is not ready yet (see [FT_LAYOUT.md](FT_LAYOUT.md)). Display Settings → **Background** uses `frame-background`; recover-vr also clears a broken empty `steamvr-pending.path` that can black-screen SteamVR after the boot logo. Launcher Configure writes/removes apps in-process in Display Settings (then host-syncs VR) so remove and the “application not available” warning stay reliable inside distrobox — see [FT_DISPLAY_SETTINGS.md](FT_DISPLAY_SETTINGS.md). SteamVR overlay clients (ft-pointer, ft-screens, ft-gaze) probe as Background before Overlay and use `Requisite=steamvr.service` so they cannot bootstrap a rogue vrserver; see `docs/design.md`. Floating windows use spare KWin outputs (`FLOAT_SLOTS`), `ft-floatd`, and `frametop.float.N` panels — see [FT_FLOATD.md](FT_FLOATD.md) and `docs/floating-windows.md`. Optional hand tracking (`hands/`, `ft-handsctl`) and screen hand cutouts are experimental and off by default — see [HANDS.md](HANDS.md).
