# FT_DISPLAY_SETTINGS

Script / app: `display-settings/ft_display_settings.py` (+ `display-settings/main.qml`, launcher `display-settings/ft-display-settings`)

## Purpose

Kirigami UI for Frametop screens, layout, visibility, SteamVR background, and Spatial Instruments. Backend talks to `@ft_screens` / `ft-layout` / `frame-background` on the host.

## Tabs (screens backend)

1. **Screens** — count, resolution, width, opacity, gaze attention, curve, anchors  
2. **Layout** — preset / capture, profiles, slots  
3. **Visibility** — when screens show (including hide-when-dashboard-opens), VR games, controllers, wrist pin  
4. **Background** — SteamVR skybox via `scripts/frame-background`  
5. **Spatial Instruments** — grid of cards with example previews; **Configure…** opens a settings sheet  

Gamescope backend omits Visibility and Spatial Instruments.

Open a specific tab with `FT_DISPLAY_PAGE=layout|visibility|instruments|background`.

## Visibility modes

| Value | Behaviour |
|-------|-----------|
| `always` | Hotkey hides |
| `dashboard` | Only while SteamVR dashboard is open |
| `except_dashboard` | Hide whenever the dashboard opens |
| `gesture` | While looking at a chosen controller |
| `toggle` | Only after hotkey show |

## Spatial Instruments UI

Built-in types (Clock, Date, Battery, Media, Device storage, SD) show as a 2-column card grid. Previews copy the real ft-screens draw style: seven-segment clock, 5×7 + seven-segment date, five battery blocks (no percent), disk/SD icon + usage bar, media title + transport glyphs. Image/Launcher cards use a transparent-checker / square-icon stand-in. Enable on the card; **Configure…** opens a settings dialog.

**Configure…** pushes a normal settings page (not a `Kirigami.Dialog` — Dialog was opening empty on the Frame). Back returns to the instrument cards.

The menu entry must launch the synced checkout (`~/dev/frametop/...`). Re-run `display-settings/install.sh` **and** `desktops.sh install` after moving the repo; an old `Exec=` pointing at `~/frametop` loads a stale `main.qml` / `ft-screens` (soft-follow and other compositor fixes never appear).

## Tests

```
bash test/test_display_settings_ui.sh
bash test/probe_configure_dialog.sh
python3 test/test_display_background_tab.py
python3 test/test_launcher_settings_api.py
python3 test/test_instrument_visibility.py
python3 test/test_instrument_configure_dialog.py
python3 test/test_gaze_attention_order.py
python3 test/test_apply_without_head.py
```
