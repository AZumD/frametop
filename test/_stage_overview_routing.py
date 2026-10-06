#!/usr/bin/env python3
from pathlib import Path

p = Path("docs/README/OVERVIEW.md")
text = p.read_text()
needle = "| `session/ft-launch.py` | [FT-LAUNCH.md](FT-LAUNCH.md) |\n"
insert = (
    needle
    + "| `session/ft-game-run` / `ft_game_run.py` | [FT-GAME-RUN.md](FT-GAME-RUN.md) |\n"
)
if "| `session/ft-game-run`" not in text:
    if needle not in text:
        raise SystemExit("anchor missing")
    text = text.replace(needle, insert, 1)
anchor2 = "| `test/run-unit.sh` | [RUN-UNIT.md](RUN-UNIT.md) |\n"
block = (
    anchor2
    + "| Stage 3 Steam→Tovakai game routing | [STEAM_GAME_ROUTING.md](STEAM_GAME_ROUTING.md) |\n"
    + "| `test/_probe_game_routing_*.sh` / `_arm_game_routing_*.sh` / `_verify_game_routing_phase5.sh` "
      "| [_PROBE_GAME_ROUTING_PHASE0.md](_PROBE_GAME_ROUTING_PHASE0.md), "
      "[_ARM_GAME_ROUTING_PHASE5.md](_ARM_GAME_ROUTING_PHASE5.md) |\n"
)
if "STEAM_GAME_ROUTING.md" not in text:
    if anchor2 not in text:
        raise SystemExit("anchor2 missing")
    text = text.replace(anchor2, block, 1)
p.write_text(text)
print("OVERVIEW updated for routing-only")
