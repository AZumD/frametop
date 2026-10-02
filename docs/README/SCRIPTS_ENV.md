# SCRIPTS_ENV

Module: `scripts/_env.sh` (sourced by other scripts; not run directly)

## Purpose

Detects whether the checkout is on the Steam Frame (`FRAME_LOCAL`) or a PC talking to it over SSH (`FRAME_HOST`, default `frame`), and sets `FRAME_REPO` / `FRAME_BOX`. Provides helpers other installers and run scripts share.

## Helpers

- `on_frame '<cmd>'` — run on the Frame host in `FRAME_REPO`
- `on_frame_script` — pipe a bash script to the Frame
- `fill_template <file>` — replace `@REPO@` with `FRAME_REPO`
- `frame_sudo '<cmd>'` — root on the Frame (TTY sudo, `SUDO_ASKPASS`, or `steamos_root_pwd` in `.env`); used by `hands/run.sh` for `setcap` on `ft-camd`
- `start_with_steamvr UNIT` — print a host snippet that restarts a user unit when SteamVR is up, otherwise leaves it for SteamVR start

## Related

[HANDS.md](HANDS.md), [RECOVER-VR.md](RECOVER-VR.md), `AGENTS.md`.

## Tests

```
python3 test/test_hands_phase3c.py
bash test/test_boot_safety.sh
```
