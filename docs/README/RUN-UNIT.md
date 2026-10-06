# RUN-UNIT

Script: `test/run-unit.sh`

## Purpose

Run the dependency-light regression suite (same list as `.github/workflows/unit.yml`). No Steam Frame hardware, SteamVR, Plasma, or PySide required.

## Usage

```
bash test/run-unit.sh
```

## Suite (keep in sync with the script)

Includes pointer/gaze/follow, Spatial Instruments, float wiring, chrome layout, and the 0.1.0 shell tests:

| Test | Doc |
|------|-----|
| `test_desktop_toolbar.py` | [TEST_DESKTOP_TOOLBAR.md](TEST_DESKTOP_TOOLBAR.md) |
| `test_toolbar_dock.py` | [TEST_TOOLBAR_DOCK.md](TEST_TOOLBAR_DOCK.md) |
| `test_toolbar_reface_on_show.py` | [TEST_TOOLBAR_REFACE_ON_SHOW.md](TEST_TOOLBAR_REFACE_ON_SHOW.md) |
| `test_taskbar_model.py` | [TEST_TASKBAR_MODEL.md](TEST_TASKBAR_MODEL.md) |
| `test_app_activity.py` | [TEST_APP_ACTIVITY.md](TEST_APP_ACTIVITY.md) |
| `test_revive_desktop.sh` | [TEST_REVIVE_DESKTOP.md](TEST_REVIVE_DESKTOP.md) |
| `test_release_packaging.sh` | [TEST_RELEASE_PACKAGING.md](TEST_RELEASE_PACKAGING.md) |

## Related

[OVERVIEW.md](OVERVIEW.md), GitHub Actions `Unit` workflow.
