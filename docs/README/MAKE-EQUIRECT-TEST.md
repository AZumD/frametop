# MAKE-EQUIRECT-TEST

Script: `scripts/make-equirect-test.py`

## Purpose

Generate a clearly marked equirectangular PNG for verifying SteamVR skybox orientation (poles, azimuth bands, seam, mirror chevron). Pure Python — no Pillow.

## Usage

```
python3 scripts/make-equirect-test.py -o ~/.config/openvr/config/frametop-backgrounds/frametop-test-equirect.png --width 2048
```

## Markers

- North pole band: cyan; south: yellow
- Azimuth: FRONT green, RIGHT magenta, BACK blue, LEFT orange (FRONT at image center)
- White right-pointing chevron at center (mirroring check)
- Red seam ticks on left/right edges
