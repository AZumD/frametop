# PROBE-EYE-ATTENTION

Script: `scripts/probe-eye-attention.sh`

## Purpose

Read-only diagnosis of the **current** ft-screens eye-gaze attention path (opacity / `GazeTarget`), not the removed desktop gaze-pointer experiment.

Reports:

- checkout `screens/actions.json` + HMD bindings, via `test/test_eye_bindings.py`
- manifests next to the running `ft-screens` binary
- recent SteamVR `vrserver` binding / eye lines
- recent `/tmp/frametop-screens.log` eye/gaze lines
- live `gaze state` from `@ft_screens` when available

## Usage

```
scripts/probe-eye-attention.sh
```

Uses `scripts/_env.sh` (`FRAME_REPO`, SSH from a PC). Does not restart SteamVR or the desktop.

## Related

[SCREENS_VR.md](SCREENS_VR.md), `test/test_eye_bindings.py`, `docs/design.md` (eye tracking).
