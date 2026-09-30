# Rebuild Screens On Frame

Rebuilds `ft-screens` on the Steam Frame inside the `dev` distrobox.

## Usage

```
scripts/rebuild-screens-on-frame.sh
```

From a PC this syncs the repo (`scripts/sync.sh` via `screens/build.sh`) then builds in `~/dev/frametop/screens/build/`. It does **not** restart the Frametop desktop or SteamVR — restart the desktop session yourself to load the new binary.

## Notes

Same build as `screens/build.sh` (OpenVR header pin, wlroots compositor + `vr.cpp`).
