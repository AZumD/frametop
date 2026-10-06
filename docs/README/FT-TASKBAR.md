# FT-TASKBAR

Script: `session/ft-taskbar.py`

## Purpose

Host side of the spatial toolbar's taskbar. ft-screens (in distrobox) draws the Start / Tasks / Displays / Tray modules and the popup overlays and does every hit test; this process supplies what needs host libraries and the nested session's D-Bus:

| Provider | Source |
|----------|--------|
| Tasks | The nested KWin's windows, through a persistent KWin script that calls `org.frametop.Taskbar /Tasks Update(json)` on every window add / remove / activate / caption / minimize / output / keep-above / fullscreen / maximize change. Each window carries its output name and its maximized, keep-above and fullscreen state. KWin 6.2 has no `maximizeMode` in scripting, so "maximized" means the frame fills `clientArea(MaximizeArea)`. The update also lists the outputs (`workspace.screens`). No process scraping. Merged with `toolbar.pinned_apps` (pinned first, one task per app). |
| Task menu | `open taskmenu TASK` (a right-click on a task tile) builds `ft_taskbar_model.task_menu_layout`. The app's own entries come from its `.desktop` file (`ft_desktop.desktop_actions`) and launch through ft-launch `command`. New window/Open uses `desktop ID`. Window commands, Send to desktop N and Close run as one-shot KWin scripts (`KWinTasks.window_op`, ops in `KWinTasks.OPS`) on all of the task's windows. Desktop N is the Nth output in screen order (`output_order`), moved with `workspace.sendClientToScreen`. Pin/Unpin edits `toolbar.pinned_apps`. |
| Start | Installed apps (`layout/ft_desktop.py`), category chips, 4×4 pages, pin toggles. Launches through `@frametop_launch`. The app list is rebuilt every time Start opens (and every 60 s), so newly installed `.desktop` files show up without restarting the session. |
| Displays | `ft-layout` profiles; the current one highlighted, slot numbers as badges. Switching runs `ft-layout profile apply NAME`. |
| Volume | Default PipeWire sink: `wpctl get-volume / set-volume / set-mute`, live through `pactl subscribe`. Uses the host `XDG_RUNTIME_DIR` (the session's is the nested one). |
| Wi-Fi | NetworkManager over the system bus (libnm, `gi.repository.NM`): enabled, signal, network list. Saved networks activate; open networks connect; secured networks without a saved secret open the network settings (`systemsettings kcm_networkmanagement`) — never a password prompt here. |

Popups are rendered with Pango / Cairo (SteamVR gamepadui palette) to `popup.png`, with hit rectangles in `popup.txt`.

Task icons in `tasks.txt` always point into `icons/` in the shared runtime directory: a resolved icon elsewhere (Flatpak exports symlink into `/var/lib/flatpak/app`, which the container can't see) is copied there first, so ft-screens never falls back to the monitor glyph for an app that has an icon.

## Wire

Abstract datagram sockets; files in `/run/user/UID/frametop-taskbar/` (shared with the container).

```
ft-screens -> @frametop_taskbar   hello | open KIND [ARG] | click KIND ID U V |
                                  scroll KIND DY | closed KIND | task ID
ft-taskbar -> @ft_screens         toolbar popup KIND SERIAL | toolbar popup-close KIND |
                                  toolbar tasks SERIAL | toolbar tray volume LEVEL PCT |
                                  toolbar tray wifi ENABLED BARS CONNECTED
```

KIND: `start`, `windows`, `taskmenu` (ARG: the task id), `profiles`, `volume`, `wifi`. `task ID` (a left click) launches, focuses, or minimizes when the task's only window already has focus. IDs are percent-encoded single tokens. `U V` are the click position inside the item (0..1; the volume slider uses `U`).

## Notes

- Started by `frametop-session.sh` inside the session's `dbus-run-session` (argv0 `ft-taskbar`, ≤15 chars), before Plasma; the KWin script is (re)loaded by a 10 s watchdog once KWin is up. Log: `/tmp/frametop-taskbar.log`.
- Find it with `pgrep -f '^ft-taskbar '` — a looser pattern also matches the session's own `dbus-run-session` command line, and killing that ends the Frametop session.
- KWin exports `loadScript(s)` and `loadScript(ss)`; the call passes `signature="ss"`.
- Every window command (focus, minimize, maximize, keep above, fullscreen, send, close) is a one-shot KWin script over a list of window ids (`window_op`), unloaded after 0.8 s.
- Pins are written to the layout (`toolbar.pinned_apps`) with `ft_layout.save_layout`.
- If libnm, dbus-python, `pactl` or KWin are missing, that provider is skipped; the rest keep working.

## Tests

```
python3 test/test_taskbar_model.py     # model, parsers, wire formats, source guards
bash test/_taskbar_smoke.sh            # throwaway ft-taskbar on the Frame; renders every popup
bash test/_taskbar_task_live.sh        # live: launch one app, see the task, close it
bash test/_task_menu_live.sh           # live: click = minimize / restore, the right-click menu's commands
bash test/_restart_ft_taskbar.sh       # restart only ft-taskbar inside the running session
```
