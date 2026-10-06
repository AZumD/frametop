# TEST_OVERLAY_BUDGET_AND_GAMES

Script: `test/test_overlay_budget_and_games.py`

## Purpose

Headless source checks: floating spare overlays stay lazy (`EnsureFloatChrome` / `ReleaseFloatChrome`); `MakePanel` early-returns for floats (no float close chrome) while real screens may create a toolbar **dock** button; AppActivity owns flatscreen/game hide and OutsideGames lasers.

## Run

```
python3 test/test_overlay_budget_and_games.py
```

Also covered by `bash test/run-unit.sh`.

## Related

[APP_ACTIVITY.md](APP_ACTIVITY.md), [FT_FLOATD.md](FT_FLOATD.md), [SCREENS_VR.md](SCREENS_VR.md), [DESKTOP_TOOLBAR.md](DESKTOP_TOOLBAR.md)
