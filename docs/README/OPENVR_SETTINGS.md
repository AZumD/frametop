# OPENVR_SETTINGS

Script: `scripts/openvr_settings.py`

## Purpose

Tiny ctypes wrapper around SteamVR `IVRSettings_003` (`libopenvr_api.so`) so tools can get/set live settings without the awkward `vrcmd --set-settings-*` CLI.

## Usage

```
python3 scripts/openvr_settings.py get-string steamvr background
python3 scripts/openvr_settings.py get-int steamvr environmentMode
python3 scripts/openvr_settings.py set-string steamvr background /path/to.png
python3 scripts/openvr_settings.py set-int steamvr environmentMode 0
```

## Notes

- Connects as `VRApplication_Utility` (falls back to Background).
- Writes through vrserver; compositor reloads skybox textures on `background` changes.
- Used by `scripts/frame-background`.
- Frame/aarch64 only: loads `/opt/steamvr/bin/linuxarm64/libopenvr_api.so`.
