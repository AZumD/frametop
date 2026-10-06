# _AUDIT_STAGE_BUGFIXES.sh

Compares `stage1-steamvr-chrome` / `stage2-desktop-toolbar` to the current tree for
already-solved bugfixes that may be missing from `stage3-steam-game-routing`.

## Usage

```
bash test/_audit_stage_bugfixes.sh
bash test/_audit_stage_bugfixes2.sh
bash test/_audit_stage_bugfixes3.sh
```

## Findings (2026-10-05)

Already present (toolbar files match stage2 tip; MakeChrome mouse-scale restored):

- Invisible laser pane (`f64f603`)
- Toolbar vanish on Start launch (`54bde43`)
- Icon band nudge / black-bar reface (`a874fd3` … `717f367`)
- Task right-click menu / OnlyShowIn helpers (partial → completed in ft_desktop)

Ported this pass:

- `scripts/sync.sh` post-rsync CR strip (`3c15206`)
- Start menu `OnlyShowIn` / Hidden stub fall-through / include NoDisplay (`0dc2f4c`, `6641826`)

Still open (needs careful vr.cpp merge with float chrome):

- SteamVR L-corner resize handle (`6bc26d0`)
- Full SteamVR chrome language polish (`ae2fe6a`) — partial constants exist; `CornerTexture` still old quarter-disc
