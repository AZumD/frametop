# TEST_REVIVE_DESKTOP

Script: `test/test_revive_desktop.sh`

## Purpose

Dependency-light guards for the 0.1.0 desktop revive path: `bash -n`, `_env.sh` usage, SteamVR / `--spares` gates, stop-then-start order, no SteamVR kill, `desktops.sh revive` wiring, and thin wrappers for the old `_fix_desktop_after_steamvr` / `_check_desktop_spares_health` helpers.

## Run

```
bash test/test_revive_desktop.sh
```

Also covered by `bash test/run-unit.sh`.

## Related

[REVIVE-DESKTOP.md](REVIVE-DESKTOP.md)
