# FRAME-BACKGROUND

Script: `scripts/frame-background`

## Purpose

Set the SteamVR compositor passive 360° background on Steam Frame using Valve’s existing settings (`steamvr.background` + `steamvr.environmentMode`), without patching `/opt/steamvr` or SteamOS.

## Commands

```
scripts/frame-background status
scripts/frame-background set ~/Pictures/foo.jpg
scripts/frame-background set aurorasky
scripts/frame-background set night_mountains
scripts/frame-background aurora
scripts/frame-background image
```

Non-PNG inputs (JPEG, WebP, Radiance `.hdr`, OpenEXR `.exr`, …) are converted with `ffmpeg` into `~/.config/openvr/config/frametop-backgrounds/<name>.png`. HDR formats are tonemapped (`tonemap=hable`) to 8-bit SDR PNG — SteamVR’s skybox loader does not take `.hdr` directly.

SteamVR’s compositor reloads the skybox on `VREvent_BackgroundSettingHasChanged`. A bare path write is sometimes ignored; `frame-background set` therefore stages the PNG under `~/.config/openvr/config/frametop-backgrounds/` and kicks Image mode by briefly toggling `environmentMode` Aurora→Image after setting the path.

`status --json` prints a machine-readable snapshot (used by Frametop Display Settings → **Background**).

## Display Settings

Frametop Display Settings has a **Background** tab that calls this CLI on the host (`distrobox-host-exec`). Presets: Aurora, Night Mountains, Aurora Sky, or a custom equirectangular image picker (Qt `QFileDialog` starting in `frametop-backgrounds/` — QML portal dialogs ignore the start folder). **Open backgrounds folder** / **Open folder** opens `~/.config/openvr/config/frametop-backgrounds/`.

## Notes

- Requires SteamVR running (talks to `IVRSettings` via `scripts/openvr_settings.py`).
- `environmentMode` 0 = Image (latlong/equirect skybox), 1 = Aurora (procedural shaders).
- Equirectangular images should be ~2:1 (e.g. 2048×1024, 4096×2048).
- Steam Frame’s dashboard UI hides solid-color background presets; the Image path still works through settings.
- SteamVR updates can change `/opt/steamvr` stock assets; user settings under `~/.config/openvr/config/steamvr.vrsettings` persist.

## Tests

```
python3 test/test_frame_background.py          # on Frame, SteamVR up
python3 test/test_frame_background_hdr.py      # offline ffmpeg HDR→PNG path
```
