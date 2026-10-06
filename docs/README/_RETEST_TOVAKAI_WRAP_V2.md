# _retest_tovakai_wrap_v2.sh

Fully automates the Tovakai wrap path (patch **v5+**): re-arms the game-route
chooser, triggers `steam://run/<appId>` (default Hades `1145360`) via CDP,
picks Tovakai, waits for `ft-game-run` / `DISPLAY=:2`, then verifies.

## Usage

```
bash test/_retest_tovakai_wrap_v2.sh
# or:
bash test/_retest_tovakai_wrap_v2.sh 1145360
```

Requires SteamVR SharedJS CDP (`:8080`) and a running Frametop desktop
(`plasmashell.env` with `DISPLAY=:2`). Does not require a manual Play press.
