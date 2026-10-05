# _restore_game_launch_options.sh

Restores Steam `strLaunchOptions` from
`/run/user/$UID/frametop-game-route/launch-options-backup.json` and deletes the
marker. Safe to run if no marker exists.

## Usage

```
bash test/_restore_game_launch_options.sh
```
