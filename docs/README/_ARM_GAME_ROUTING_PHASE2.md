# _arm_game_routing_phase2.sh

Temporary SharedJS CDP inject for **Phase 2** only:

1. On `LaunchApp` for one app id (default **Hades** `1145360`)
2. `CancelGameAction` immediately
3. After 500 ms, `RunGame(gameId, "", -1, launchSource)` stock
4. One-shot bypass so the relaunch is not cancelled again

Does **not** mutate launch options or wrap for Tovakai.

## Usage

```
# Quit the game first if it is running, then:
bash test/_arm_game_routing_phase2.sh          # Hades
bash test/_arm_game_routing_phase2.sh 1145360  # explicit

# Launch the game once from SteamVR, wait until it is up, then:
bash test/_dump_game_routing_phase2.sh
```

Dispose: evaluate `__ftGameRouteP2.dispose()` in SharedJS, or reload SharedJS.

See [STEAM_GAME_ROUTING.md](STEAM_GAME_ROUTING.md).
