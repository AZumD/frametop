# _wait_pick_game_route.sh

Waits for a pending game-route chooser (user presses Play), then CDP-picks a route.

## Usage

```
# In headset: press Play on Hades, then on PC:
bash test/_wait_pick_game_route.sh tovakai
bash test/_wait_pick_game_route.sh steamvr
```

Optional timeout (seconds, default 90):

```
bash test/_wait_pick_game_route.sh tovakai 120
```

See [_PICK_GAME_ROUTE_CHOOSER.md](_PICK_GAME_ROUTE_CHOOSER.md), [_ARM_GAME_ROUTE_CHOOSER.md](_ARM_GAME_ROUTE_CHOOSER.md).
