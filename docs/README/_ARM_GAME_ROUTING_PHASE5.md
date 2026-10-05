# _arm_game_routing_phase5.sh

Syncs FrameTop, checks nested `plasmashell.env`, installs a **temporary** Steam
launch-options wrap (`ft-game-run %command%`) for one app (default Hades), writes a
restore marker, and disarms Phase 2 cancel/relaunch if still loaded.

## Usage

```
# Frametop desktop must be up
bash test/_arm_game_routing_phase5.sh          # Hades
bash test/_arm_game_routing_phase5.sh 1145360

# Launch the game once from SteamVR, then:
bash test/_verify_game_routing_phase5.sh
```

Emergency undo without verify:

```
bash test/_restore_game_launch_options.sh
```

See [STEAM_GAME_ROUTING.md](STEAM_GAME_ROUTING.md), [FT-GAME-RUN.md](FT-GAME-RUN.md).
