# Profiles, gaze, and future gestures (iteration 3)

## Shared actions

Profile switching must stay on one path:

- VR chrome slot circles → `ft-layout action profile.slot.N`
- Hide/show screens → `screens.toggle`
- Spatial Instruments → Display Settings tab; Clock is the first type (`ft-layout instrument …`)
- SteamVR digital keyboard → removed for now (chrome "K" / ShowKeyboard path withdrawn)
- Aurora / passthrough → not exposed (no public OpenVR API for overlay apps)
- Input Settings button maps → same aliases (`profile_slot_N`, `profile_next`, …)
- Display Settings / Quickshell → canonical dotted names

Do not reimplement profile JSON apply in the relay, chrome, or future hand code.

## True eye gaze (Steam Frame)

Frametop uses OpenVR eye tracking, not HMD forward as fake pupils:

- Manifest: `screens/actions.json` (`/actions/frametop/in/EyeGaze`, type `eyetracking`)
- Default bindings: `screens/bindings_frame_hmd.json` / `bindings_hmd.json` (copied next to `actions.json` in `screens/build/` at build time). SteamVR requires a top-level `"eyetracking": [{ "path", "output" }]` array — not a `sources`/`mode` entry. Driver component is `/eyetracking`, so the bind path is `/user/head/eyetracking`.
- API: `IVRInput::GetEyeTrackingDataRelativeToNow` (falls back to `…ForNextFrame`)
- Runtime: `allowEyeTracking` is on in the Frame HMD defaults; the `eyetracking` server (`start_eyetracking.sh`) must be running
- States: unavailable / temporarily invalid / valid (never crash if missing)
- Debug: `ft-layout gaze state` (includes `err=` / `flags=`), `gaze debug on|off`, `gaze fallback head|off`

If `gaze state` stays `eye=0`, check `vrserver.txt` for `ft-screens (frame_hmd) has no configured binding` — usually the binding JSON was missing from `screens/build/` or the shape/path was wrong.

Head fallback is **debug only**. Production attention fading requires valid eye samples.

## Gaze targeting

`GazeTarget` picks the closest hit along the gaze ray: screen surface, chrome controls, profile slots. Gaze focuses and drives optional attention fade. It does not click, and it does not reveal the bottom chrome (laser / 3D mouse only for now).

Future pinch / finger tracking should call conceptual helpers (`activateCurrentGazeTarget`, gaze-drag begin/update/end) against the current target — chrome → semantic Frametop action; screen surface → desktop pointer at mapped UV/pixels.

Screen UV → desktop pixel mapping is exposed in `gaze state` when the target is a screen (`u`, `v`, `pixel=` = surface-local logical; `buffer_pixel=` = DMA-BUF). Laser clicks and future gaze+pinch share `screens/coords.h`. Do not move the system mouse from gaze alone yet.

## Opacity / attention

Per screen: `activeOpacity`, `idleOpacity`, `attentionEnabled` (+ fade timings). Legacy `opacity: X` → both active and idle = X, attention off. Final alpha = `attentionResolved × visibilityFade` in one composer inside ft-screens. Fade-in / fade-out speeds (`attention.in_ms` / `attention.out_ms`) are set in Frametop Display Settings when gaze attention is on — there is no VR chrome opacity slider.

## Free-air gestures (later)

Reliable bare-hand profile flicks remain risky. Prefer chrome + controller actions now; add pinch confirmation once hand tracking is solid.
