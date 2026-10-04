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

## Screens shown

On the Visibility tab, under **Screens shown** (before "Screens on a wrist or head"), each screen has a **Shown / Hidden** switch (`backend.screensShown`, `backend.setScreenShown(index, shown)` → `ft_layout.set_hidden`). A hidden screen stays hidden whatever the visibility mode says, and the hotkey doesn't bring it back; the windows on it stay there. It is saved as `"hidden": true` in the layout and sent to ft-screens as `conceal N` / `reveal N` when the desktop runs. Spatial Instruments are not affected.

## Spatial Instruments UI

Built-in types (Clock, Date, Battery, Media, Device storage, SD) show as a 2-column card grid. Previews copy the real ft-screens draw style: seven-segment clock, 5×7 + seven-segment date, five battery blocks (no percent), disk/SD icon + usage bar, media title + transport glyphs. Image/Launcher cards use a transparent-checker / square-icon stand-in. Enable on the card; **Configure…** pushes a settings page (not a `Kirigami.Dialog` — Dialog was opening empty on the Frame). Back returns to the instrument cards.

**Launcher Configure:** picking an application writes `desktop_id` into the shared layout **in-process** (so the unavailable warning and editor refresh immediately), then syncs VR via host `ft-layout`. `backend.isAppInChooser(desktopId)` drives the “not available” warning (avoids fragile QML `===` on QVariantMap ids). **Remove** also updates the layout in-process then pops the page (same pattern as Image); host-exec only refreshes live overlays. `host_command` quotes through `sh -c` so `.desktop` ids with spaces survive `distrobox-host-exec`.

The menu entry must launch the synced checkout (`~/dev/frametop/...`). Re-run `display-settings/install.sh` **and** `desktops.sh install` after moving the repo; an old `Exec=` pointing at `~/frametop` loads a stale `main.qml` / `ft-screens` (soft-follow and other compositor fixes never appear).

## Tests

```
bash test/test_display_settings_ui.sh
python3 test/test_display_background_tab.py
python3 test/test_launcher_settings_api.py
python3 test/test_launcher_remove_and_apps.py
python3 test/test_instrument_visibility.py
python3 test/test_instrument_configure_page.py
python3 test/test_gaze_attention_order.py
python3 test/test_apply_without_head.py
python3 test/test_screen_conceal.py
```
