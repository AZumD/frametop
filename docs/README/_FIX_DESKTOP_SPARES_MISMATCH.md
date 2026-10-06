# _fix_desktop_spares_mismatch.sh

Rebuild `ft-screens` on the Frame so it accepts `--spares`, then smoke-test and
start the nested desktop.

## When to use

After a SteamVR restart (or a source sync) the desktop fails to open and
`/tmp/frametop-screens.log` only shows the `usage:` line. That happens when
`session/frametop-session.sh` passes `--spares N` but the Frame binary was built
from a tree that did not implement that flag (session synced, screens not
rebuilt).

Does **not** restart SteamVR/gamescope.

## Usage

```
bash test/_fix_desktop_spares_mismatch.sh
```

## Related

- `_diagnose_desktop_after_steamvr.sh` — read-only health check
- `_fix_desktop_after_steamvr.sh` — stop + start without rebuild
- `_check_desktop_spares_health.sh` — quick binary/proc/socket check
- `_start_desktop_after_spares_rebuild.sh` — smoke + start when binary already has `--spares`
- `scripts/rebuild-screens-on-frame.sh` / [REBUILD-SCREENS-ON-FRAME.md](REBUILD-SCREENS-ON-FRAME.md)
