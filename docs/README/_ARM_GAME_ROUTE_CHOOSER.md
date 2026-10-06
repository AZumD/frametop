# _arm_game_route_chooser.sh

Syncs FrameTop and injects `steam-ui-patches/game-route/patch.js` into SharedJS via CDP.

## Usage

```
bash test/_arm_game_route_chooser.sh
# Launch a flat 2D game from SteamVR → chooser
bash test/_dump_game_route_chooser.sh
bash test/_disarm_game_route_chooser.sh
```

If the popup is not visible in VR, pick via CDP:

```
window.__ftGameRoute.pick('steamvr'|'tovakai'|'cancel')
```

See [STEAM_GAME_ROUTING.md](STEAM_GAME_ROUTING.md), `steam-ui-patches/game-route/README.md`.
