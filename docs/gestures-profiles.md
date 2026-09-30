# Profiles, gaze, and future gestures (iteration 3)

## Shared actions

Profile switching must stay on one path:

- VR chrome slot circles → `ft-layout action profile.slot.N`
- Hide/show screens → `screens.toggle`
- Spatial Instruments → Display Settings tab; Clock, Date, Battery, Device storage, SD, Media (`ft-layout instrument …`)
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

`GazeTarget` picks the closest hit along the gaze ray among screen surfaces, chrome controls, and profile slots. Spatial Instruments are only considered when that ray misses every screen/chrome — otherwise a nearby clock/battery/storage steals the hit and pulses display attention. Gaze focuses and drives optional attention fade. It does not reveal the bottom chrome (laser / 3D mouse only for now).

OpenVR eye samples often drop for tens of milliseconds. ft-screens keeps the last valid ray for ~450 ms (`held` in `gaze state` / debug) so attention and the gaze reticle stay put through those gaps.

### Gaze pointer mode (prototype)

Headset-button + eye gaze can drive the nested desktop cursor without a controller:

1. Press the headset button once → activate; cursor appears at filtered gaze on a **screen** surface.
2. Further presses → left click at the current pointer (mode stays active).
3. ~10s without meaningful filtered move or button → auto-deactivate (cursor leave).

Filtering (in `ft-screens`): raw UV → One Euro → seat pixels → small deadzone (jitter only; **no** UI snapping) → existing `ft_event` → wlroots seat. Opacity/attention gaze keeps running when the pointer is inactive.

The pointer **auto-hides** after `GAZE_POINTER_TIMEOUT` seconds (`frametop.conf`, or `ft-layout gaze pointer timeout`) with **no headset-button click**. Looking around or seat motion does not refresh that timer; activation and each click do.

While active, ft-screens shows a cyan **Frametop gaze reticle** (`frametop.gaze.cursor`) on the screen surface at the filtered (+ calibrated) gaze point (KWin’s host cursor is not composited onto panels). `ShowOverlay` runs every frame while placing; a ~550 ms hold keeps the last UV through brief miss/dropout. In hybrid mode a faint pad ring (`frametop.gaze.pad`) marks the eye-nudge circle around the head aim.

While gaze-pointer is active, ft-screens hides SteamVR’s `system.pointer` / `system.cursor` variants. Aiming a controller at a panel ends gaze mode; tip alpha/width are restored (`FT_LASER_TIP_M`).

### Gaze pointer modes

- **Off** (`GAZE_POINTER=0`): headset button is SteamVR’s head-locked laser (vanilla).
- **Full gaze** (`GAZE_POINTER_MODE=gaze`): reticle follows filtered eye UV on a screen.
- **Hybrid** (`GAZE_POINTER_MODE=hybrid`): head ray sets the pad centre; eyes nudge inside a UV circle with a large centre deadzone, reduced eye gain, and heavy offset smoothing (`GAZE_POINTER_PAD_UV` default 0.08, `PAD_DEADZONE` 0.50, `EYE_GAIN` 0.35). A faint ring shows the pad.

CLI: `ft-layout gaze pointer mode off|gaze|hybrid`, `gaze pointer pad 0.08`, `gaze pointer eyegain 0.35`, `gaze pointer paddeadzone 0.50`. Conf: `GAZE_POINTER_*` in `session/frametop.conf.example`.

### Gaze calibration

`ft-layout gaze pointer calibrate start` places five orange crosshairs on the first screen. Look at each and press the headset button. ft-screens averages `expected UV − measured UV` into an additive bias (`GAZE_POINTER_CAL_U` / `CAL_V`, also `gaze pointer caloffset`). This is a Frametop bias on top of SteamVR’s eye tracking — not a full geometric remapping.

Button path: `input-relay` **grabs** host `gpio-keys` (EVIOCGRAB is device-wide) so SteamVR no longer receives `KEY_SELECT` (353) and does not summon its head laser. `KEY_SELECT` → `gaze pointer button` on `@ft_screens`. Other keys on that node (at least `KEY_VOLUMEUP`) are re-emitted onto `frametop virtual keyboard` (already held by SteamVR). Configure mode via `GAZE_POINTER_*` in `frametop.conf` / `ft-layout gaze pointer …`; `reload` on `@frametop_relay` applies grab/ungrab live — off restores vanilla SteamVR head-locked laser on the headset button. Set `GAZE_POINTER_GRAB=0` only for debugging (Valve laser will compete again). Override device/code with `GAZE_POINTER_BUTTON_DEVICE` / `GAZE_POINTER_BUTTON_CODE`.

Screen UV → seat mapping remains in `gaze state` (`pixel=` / `buffer_pixel=`) via `screens/coords.h`.

Future pinch / finger tracking can still call `activateCurrentGazeTarget` for chrome semantic actions; this prototype is screen-surface mouse only.

## Opacity / attention

Per screen: `activeOpacity`, `idleOpacity`, `attentionEnabled` (+ fade timings). Legacy `opacity: X` → both active and idle = X, attention off. Final alpha = `attentionResolved × visibilityFade` in one composer inside ft-screens. Fade-in / fade-out speeds (`attention.in_ms` / `attention.out_ms`) are set in Frametop Display Settings when gaze attention is on — there is no VR chrome opacity slider.

## Free-air gestures (later)

Reliable bare-hand profile flicks remain risky. Prefer chrome + controller actions now; add pinch confirmation once hand tracking is solid.
