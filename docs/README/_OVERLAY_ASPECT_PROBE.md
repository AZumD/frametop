# _overlay_aspect_probe.sh

Builds and runs `test/overlay_aspect_probe.cpp` on the Frame: checks whether
SteamVR hit-tests `SetOverlayRaw` overlays by texture aspect or as squares, with
and without `SetOverlayMouseScale`. Overlays are alpha 0, placed under the floor,
and destroyed immediately.

## Usage

```
bash test/_overlay_aspect_probe.sh
```
