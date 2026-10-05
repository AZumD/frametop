# _probe_game_routing_observe.sh

Temporarily injects an **observe-only** `SteamClient.Apps.RegisterForGameActionStart`
listener into SharedJSContext via CDP (`:8080`). Does not cancel or alter launches.

## Usage

```
bash test/_probe_game_routing_observe.sh
# launch a non-VR 2D game from SteamVR once
bash test/_dump_game_routing_probe.sh
```

Log lives in `window.__ftGameRouteProbe` until SharedJS reloads.
Dispose: evaluate `__ftGameRouteProbe.dispose()` in SharedJS, or reload SharedJS.

See [STEAM_GAME_ROUTING.md](STEAM_GAME_ROUTING.md).
