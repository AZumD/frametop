# TEST_APP_ACTIVITY

Script: `test/test_app_activity.py`  
Harness: `test/app_activity_harness.cpp` (optional; needs g++)

## Purpose

Dependency-light ownership tests for `screens/app_activity.h`: Desktop vs VrScene vs FlatGamePresentation, the gamepad-mode latch, OutsideGames laser rules, and source guards that `vr.cpp` wires hide + lasers through one decision. Compiles the C++ harness when `g++` is available; skips that case otherwise (WSL/CI without a compiler still pass the Python twin).

## Run

```
python3 test/test_app_activity.py
```

Also covered by `bash test/run-unit.sh`.

## Related

[APP_ACTIVITY.md](APP_ACTIVITY.md), [SCREENS_VR.md](SCREENS_VR.md), [RUN-UNIT.md](RUN-UNIT.md)
