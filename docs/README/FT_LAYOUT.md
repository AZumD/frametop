# FT_LAYOUT

Script / module: `layout/ft_layout.py` (CLI `layout/ft-layout`)

## Purpose

Arrange Frametop virtual screens, push visibility / follow / Spatial Instruments to `ft-screens`, and apply KWin output scales so the VR pointer matches Display Settings scale.

## Apply resilience

`ft-layout apply` (and the desktop startup `--wait` path) must keep working when SteamVR has not yet published an HMD pose:

1. **Visibility first** — `except_dashboard` and related settings are sent before place, so dashboards hide desktop even if arrange is deferred.
2. **Head pose retries** — `read_head_pose` retries; if still missing, screens/instruments place from a fallback eye `(0, 1.5, 0)` and yaw `0` (re-run `apply` once tracking is up for a correct origin).
3. **Scales after apply** — KWin scales + `scale N` to ft-screens still run when arrange raises, so pointer seat mapping stays correct at fractional scales (e.g. 1.25).
4. **Instruments** — pushed from layout even without head pose; overlay keys left after a hard kill are reclaimed in `screens/vr.cpp` (`CreateOrRecycleOverlay`).

## Usage

```
layout/ft-layout apply [--wait SEC] [--duration MS]
layout/ft-layout scale
layout/ft-layout instrument list|enable|…
```

## Tests

```
python3 test/test_apply_without_head.py
python3 test/test_pointer_coords.py
python3 test/test_instrument_visibility.py
python3 test/test_spatial_instruments.py
```
