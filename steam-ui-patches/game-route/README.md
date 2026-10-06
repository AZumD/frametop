# GAME-ROUTE (steam-ui-patches)

Steam-facing launch chooser: SteamVR vs Tovakai.

## Ownership

| Piece | Lives in |
|-------|----------|
| Intercept / chooser UI / temp launch options | This patch (`steamFrame.uiPatches.patches`) — ultimately **steam-frame-nix** |
| `ft-game-run` display redirect | FrameTop `session/ft-game-run` |

## Files

- `patch.js` — SharedJSContext inject
- `unpatch.js` — dispose

## Temporary install (CDP)

Until wired into `~/nix-config` / home-manager:

```
bash test/_arm_game_route_chooser.sh
bash test/_dump_game_route_chooser.sh
bash test/_pick_game_route_chooser.sh tovakai   # when popup not visible in VR
bash test/_disarm_game_route_chooser.sh
```

## Tovakai relaunch note

`Apps.RunGame` does **not** apply `SetAppLaunchOptions` / `%command%` wraps (proven
2026-10-05). The patch (v2+) sets the wrap, verifies it, then relaunches via
`SteamClient.URL.ExecuteSteamURL('steam://run/<appId>')` so Steam rebuilds the
launch line through the same path as Play. If that fails it leaves the wrap +
bypass and waits for a manual Play.

v3+: `__ftGameRoute.pick` is always a function; use `__ftGameRoute.pending()` to
see if a chooser is waiting.

v4: call `SteamClient.URL.ExecuteSteamURL(url)` on the object (extracting the
function loses `this` and throws `Unknown method`).

v5: delay options restore (~18s). Restoring at 2.5s cleared the wrap before
Steam's `CreatingProcess` (proven: `steam://run` applies wraps only if they
remain until then).

## Nix shape (target)

```nix
steamFrame.uiPatches.patches = [ {
  name = "game-route";
  target.title = "SharedJSContext";
  state = true;   # crash recovery of launch options via __sfuiStore
  patch = ./game-route/patch.js;  # or mkPatch wrapper
  unpatch = ./game-route/unpatch.js;
} ];
```

See [STEAM_GAME_ROUTING.md](../docs/README/STEAM_GAME_ROUTING.md).
