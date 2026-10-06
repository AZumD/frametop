# TEST_DESKTOP_TOOLBAR

Script: `test/test_desktop_toolbar.py`

## Purpose

Dependency-light checks for `layout/ft_toolbar.py`: default taskbar modules (Start / Tasks / Displays / Tray), legacy default-strip migration, sanitize defaults (toolbar **enabled by default** for 0.1.0), layout widths / side packing, and restore socket commands. No OpenVR.

## Run

```
python3 test/test_desktop_toolbar.py
```

Also covered by `bash test/run-unit.sh`.

## Related

[DESKTOP_TOOLBAR.md](DESKTOP_TOOLBAR.md), [TEST_TOOLBAR_DOCK.md](TEST_TOOLBAR_DOCK.md), [TEST_TASKBAR_MODEL.md](TEST_TASKBAR_MODEL.md), [RUN-UNIT.md](RUN-UNIT.md)
