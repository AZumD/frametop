# FT_TASKBAR_MODEL

Module: `layout/ft_taskbar_model.py`

## Purpose

Pure-Python model behind the toolbar taskbar (no Qt, Cairo or D-Bus), so it is unit-tested anywhere. `session/ft-taskbar.py` renders and runs the providers on top of it; `screens/toolbar_taskbar.inc` mirrors the click and popup rules.

## Contents

| Part | Functions |
|------|-----------|
| Tasks | `app_index`, `window_app` (match a KWin window to an app: desktop file name, then `StartupWMClass`, then resource class), `merge_tasks` (pinned first in pin order, then running apps, one task per app, its windows, focused flag), `task_click` (`launch` / `focus` / `minimize` when its only window already has focus / `expose`), `toggle_pin`, `output_order` (KWin output names in Frametop screen order, natural sort like `ft_layout.outputs`) |
| Task menu | `task_menu_layout(task, actions, outputs, can_launch)`: the right-click menu, in groups. First the app's `.desktop` actions and New window (Open when not running); then Minimize/Restore, Maximize/Restore size, Keep above others, Fullscreen; then Send to desktop N for every screen the windows aren't all on already; then Pin/Unpin from taskbar; then Close window / Close all N windows. Window commands act on all of the task's windows, and the labels and toggle states follow them. |
| Popups | `PopupState` (one at a time; the same popup toggles; click-away and hiding close it), `POPUP_KINDS` |
| Start menu | `start_categories` (chips with at least one app), `start_page` (4×4 pages, clamped) |
| Layouts | `start_layout`, `volume_layout`, `wifi_layout`, `profiles_layout` (ft-layout's slot list or a mapping), `windows_layout`, `list_layout` — pixel rects at 1000 px per metre |
| Providers | `parse_wpctl_volume`, `parse_wpctl_description`, `volume_glyph_level`, `signal_bars`, `merge_networks` (one row per SSID, strongest, active first, stable keys), `network_click` (`activate` / `connect-open` / `settings`) |
| Wire | `wire_id`, `items_text` (popup.txt), `tasks_text` (tasks.txt) |

## Notes

- `network_click` never asks for a secret: a secured network that is not saved goes to the system network settings.
- Disabled items are left out of `popup.txt`, so they cannot be clicked.
- In `start_layout` the pin toggle sits on top of its app tile; ft-screens' hit test takes the last matching rect.

## Tests

```
python3 test/test_taskbar_model.py
```
