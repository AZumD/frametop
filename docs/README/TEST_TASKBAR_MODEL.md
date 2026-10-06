# TEST_TASKBAR_MODEL

Script: `test/test_taskbar_model.py` (plus the Frame helpers below)

## Purpose

Dependency-light tests for the toolbar taskbar: task merge and de-duplication, click decisions (launch / focus / minimize a focused single window / expose), output screen order, the task right-click menu (groups and order, Send to desktop N skips the desktop the windows are on, state labels, pinned-not-running and unknown-app variants), `.desktop` action parsing, pins, popup exclusivity and closing rules, popup layouts (every rect inside its popup, unique ids), wpctl / network parsing, the no-password Wi-Fi rule, the ft-screens wire formats, and source guards on the C++ side (popup sort order, bottom-left mouse flip, topmost hit rect, close on hide and click-away, defaults equal to `ft_toolbar.DEFAULT_GROUPS`, no `gamepadui.main`, no gaze cursor) and on the session script.

## Run

```
python3 test/test_taskbar_model.py
bash test/run-unit.sh   # includes this file plus toolbar / dock / AppActivity
```

## Frame helpers

| Script | What it does |
|--------|--------------|
| `test/_taskbar_smoke.sh` | Sync; throwaway `ft-taskbar` in its own `dbus-run-session`; opens every popup kind; copies the PNGs to `build/taskbar-smoke/`. Does not touch the desktop. |
| `test/_deploy_taskbar.sh` | Tests, sync, rebuild ft-screens, **restart the Frametop desktop**, re-apply the toolbar, live popup open / swap / toggle checks. `START_ONLY=1` only starts the desktop and checks. |
| `test/_taskbar_task_live.sh` | Launches one small app, checks it appears as a task and the strip grows, closes it with a one-shot KWin script. |
| `test/_task_menu_live.sh` | Opens Chromium and drives the running ft-taskbar: renders the right-click menu (`build/task-menu.png`), click = minimize / restore, Send to desktop 2 and back, Keep above on / off, Close. Prints KWin's window state after each step. |
| `test/_kwin_api_probe.sh` | Opens Dolphin, prints which KWin scripting properties the window menu can use, closes it. |
| `test/_restart_ft_taskbar.sh` | Restarts only `ft-taskbar` inside the running session. |
| `test/_taskbar_audio_probe.sh` | Read-only: default sink, level, name. |
| `test/_vr_health_probe.sh`, `test/_session_end_probe.sh` | Read-only health / why-did-the-session-end probes. |
