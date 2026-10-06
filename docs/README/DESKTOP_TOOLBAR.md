# DESKTOP_TOOLBAR

Modules: `screens/desktop_toolbar.inc`, `screens/toolbar_dock.inc`, `screens/toolbar_taskbar.inc`, `screens/spatial.inc` (all included from `screens/vr.cpp`), `screens/steamvr_assets.cpp`, `layout/ft_toolbar.py`

## Purpose

Frametop-owned spatial desktop toolbar. Borrows SteamVR **ControlBar / LegacyDashboardBar composition** (module tiles, hierarchy, silhouette); does **not** use, inject into or reparent Valve dashboard overlays. It is the dock anchor screens can be docked to.

## SteamVR grammar (from installed CSS)

Read from `/opt/steamvr/resources/webinterface/dashboard/css` on the Frame:

| Token | Value |
|-------|--------|
| `--dashboard-control-bar-width/height` | 1800×180 |
| Bar background | `--gamepadui-darkest-grey` `#0e141b` |
| Group background | `--gamepadui-darker-grey` `#23262E` |
| Button face | `--gamepadui-dark-grey` `#3D4450` |
| Active accent | `#88ccf1` (2px outline / underline) |
| `.ControlBarGroup` | padding 7px, radius 9001px; `.Large` radius 21px |
| `.ControlBarButton` Small | 85px; `.Large` buttons radius 16px |
| Section spacing | `--dashboard-control-bar-control-spacing` 1rem |

## Architecture

```
            [ docked screen 1 ]   [ docked screen 2 ]      <- toolbar_dock.inc
   ┌ popup ┐                                               <- toolbar_taskbar.inc
[ Start ] [ pinned + running apps … ]   [ Displays ] [ volume  Wi-Fi ]
                       ( move bar )                          <- the screens' grab pill
```

Default modules (`ft_toolbar.DEFAULT_GROUPS`): left `start`, `tasks`; right `displays`, `tray`. Each side is packed against its end of the bar (`PlaceToolbar`, mirrored by `ft_toolbar.side_starts`): left modules from the left end, right modules up to the right end, center modules centred and clamped between the two. The bar is a rounded rectangle (`MainControlBar`'s 30px radius on 180px), fully opaque at full opacity. Items have no containers: there are no group plates, and an idle cell is the bar's own colour (`CellFill`), lighting to the button grey with the accent ring when targeted. The Start button shows the Tova icon (`screens/assets/start-icon.png`, made by [MAKE_START_ICON.md](MAKE_START_ICON.md); the four-squares glyph if the file is missing).
- **Arch shape and tilt.** Seen straight on, the bar is an arch: a band of constant thickness bent through ±`kArchDeg` (15°) around a centre below it, with its ends cut radially (`Arch`, `ArchTexture`). The backing is painted with that arch as soon as it is created (`EnsureToolbar`); `UploadToolbarBacking` redraws it when the width changes and resets the mouse scale. **`MakeChrome` must call `SetOverlayMouseScale` to the texture size** (stage2 `f64f603`): SteamVR hit-tests by mouse-scale aspect, and the default 1×1 turns a wide bar into a large invisible square that blocks lasers. Cells sit on the band and **roll with it** (`ToolbarOnArch(..., roll=true)`), nudged inward by `kCellBandNudge` (0.08 of the band thickness) so icons read in the middle of the bar; popups hang upright above their cell, facing the head. Icon glyphs are drawn 2 texels below the tile centre. Seen from above, the bar still follows the head-distance arc (`g_toolbar.curve`) that docked screens use — backing curvature uses `metres` (same arc as the cells), not the slightly wider texture bounds. Its visuals tilt back `kTiltBackDeg` (20°) past facing the eye. The gaze and laser-proximity regions cover the arch's full extent. Preview the shape with `python3 test/_arch_preview.py [metres] [scale]`. The older modules (`home`, `launcher`, `profiles` 1–6, `action`, `user`) can still be configured; a saved toolbar that still has the previous default strip is moved to the taskbar default.
- **Task rebuild / reface.** When the running-app set changes (for example launching from Start), only the module cells are destroyed and rebuilt (`DestroyToolbarCells`). The backing and move bar stay, so the bar never flashes blank. **`ShowToolbar(true)` always re-faces every cell** (and `LightToolbarBtn` resets mouse scale after each upload), so dashboard yield Hide/Show and recycled overlays cannot leave blank icons. Closing a popup also keeps attention awake for ~0.75 s (`interactUntil`) so looking at the new window does not slam the bar to idle mid-rebuild. Cells sit `kBtnDz` (3 cm) in front of the backing so the curved mesh cannot swallow them.

- **One spatial body.** `DesktopToolbar : FollowState, AttentionState, MoveDrag` — the same structs and functions (`spatial.inc`) screens and Spatial Instruments use: `ApplyFollowMode`, `RepinInPlace`, `StepSoftFollow` (incl. dead zone), `StepAttention`, `BeginMoveDrag` / `MoveDragPose` / `EndMoveDrag`. No follow or attention math lives in the toolbar files.
- **Dock anchor.** The body's pose is kept upright (yaw + position, `YawOnlyHead`). Only the bar's visuals pitch to face the eye (`ToolbarVisualPose`); the arc radius is the head's horizontal distance, refreshed when the toolbar settles (placed, recentred, carried).
- **Move bar.** A grab pill under the bar (same texture and idle / hover / active rules as a screen's bar, twice the hit height). Grab = `BeginMoveDrag`; the body is levelled every frame while carried; release = `EndMoveDrag`, which re-pins the soft follow mode in place, then `ft-layout toolbar capture` saves it. Scroll while carrying pushes / pulls.
- **Attention.** True eye gaze on the bar or its move bar (`GazeKind::Toolbar`, no gaze cursor); a laser on any toolbar control wakes it at once. Docked screens keep their own opacity.
- **Scale** multiplies every module length (`TS()`).
- **Dashboard yield.** `ToolbarWanted()` is false while the SteamVR dashboard is open (or the screens are hidden); the toolbar and its docked screens hide together. Transforms stay current while hidden, so nothing jumps on return.

### Docking (`toolbar_dock.inc`)

- Every screen has a **Dock to dashbar** button (chrome row, right of roll). Glyphs: SteamVR's `Minimize` (dock) and `Popout` (undock) 36×36 icon outlines, re-drawn as polygons in code (`kDockBar`, `kDockChevron`, `kUndockArrow`, `kUndockBox`); no Valve asset is copied.
- Dock: `preDock = FollowState` (pose, follow mode, relative pose, rigid pin, dead zone), the screen becomes a world body driven by the anchor. Undock: the whole `FollowState` is put back (rigid pins re-attach; soft follow continues from the exact pre-dock pose). Width, curve and opacity are never touched.
- **Fly animation.** Dock, undock, and slot reshuffles ease over `kDockAnimSec` (0.450 s) with the same cosine ease-in-out as `ft-layout profile apply` (`DEFAULT_PROFILE_DURATION_MS`). Docked screens lerp from their start pose toward the live slot target each frame (so the end can move with the toolbar); undock flies in world space to the pre-dock pose, then restores follow. Remaining docked screens ease sideways when the group changes.
- Placement: docked screens stand above the bar top + `kDockLift` + their own chrome clearance, side by side in **stable slots** (dock order), centred, on the toolbar's cylinder; a group wider than `kDockSpanRad` is pushed back. SteamVR itself docks one panel at an exclusive "Dashboard" location; Frametop allows several.
- A docked screen's move bar carries the toolbar (the whole group); roll and the follow cycle are off while docked. Turning the toolbar off undocks everything.
- `get N` reports the pre-dock state while docked, so captures and profiles never save a docked pose.

### Taskbar (`toolbar_taskbar.inc` + `session/ft-taskbar.py`)

- **Split.** ft-screens owns everything spatial: module tiles, the popup overlay, the hover highlight, hit tests, click-away. `ft-taskbar` (host, nested D-Bus) owns the data and renders popup images ([FT-TASKBAR.md](FT-TASKBAR.md)). Model and rules: [FT_TASKBAR_MODEL.md](FT_TASKBAR_MODEL.md).
- **Start** (app tile, 2×2 squares glyph) opens the applications popup: category chips, 4×4 icon + name grid, pages (scroll or ‹ ›), a pin toggle per app. Launching closes it. No search field (no text entry in a VR popup yet).
- **Tasks**: one app tile per task, pinned first, then running apps, de-duplicated per app. Icon from the app's theme icon; a short accent underline = running, full underline = focused. Click: launch (pinned, not running), focus (one window), minimize (one window that already has focus), or a **windows** popup to pick one (several windows). Right-click (`VRMouseButton_Right`) opens the task's **taskmenu** popup, the window menu ft-taskbar builds (see FT-TASKBAR.md). The task source is the nested KWin (a KWin script), never process scraping. Pins persist in `toolbar.pinned_apps`; no drag reordering. A changed task set rebuilds the strip (deferred while the toolbar is carried); focus / window-count changes only redraw tiles.
- **Displays** (monitor glyph) opens the profile list on the existing ft-layout backend, current profile highlighted, slot badges, "Display Settings…" at the bottom.
- **Tray**: volume (speaker glyph with 0–3 waves, muted cross) and Wi-Fi (fan with signal arcs, slash when not connected). Their popups: mute + slider (click or drag) + "Sound settings…"; Wi-Fi toggle + networks + "Network settings…". Providers are separate classes in `ft-taskbar`, so further tray items add a provider, a glyph and a layout.
- **Popups.** One at a time (`OpenPopup` closes the previous one; the same button toggles). Anchored above their button and 3 cm in front of it. Each popup stands upright and square to the line to the head on both axes (`FacingHead`), not to the bar's tilt or arc, and follows the toolbar and the head every frame (`PlaceTaskbarPopup` from `PlaceToolbar`). Sort 4 (popup) / 5 (highlight, no input) above the toolbar's cells. Close on click-away (a trigger press on neither the popup nor the toolbar), when the toolbar hides (dashboard, desktop mode), when its button disappears, or when ft-taskbar asks (after launching). While a popup is open the toolbar counts as interacting (full opacity). OpenVR mouse coordinates are bottom-left origin and are flipped; the last matching rect wins.
- Gaze stays attention-only; there is no gaze cursor.

## Config

Default **on** for 0.1.0 (`layout` `DEFAULTS` and `sanitize_toolbar` / `default_toolbar`). Only an explicit `"enabled": false` (or `ft-layout toolbar disable`) turns it off. Missing toolbar keys in a layout are filled with the taskbar default groups.

```json
"toolbar": {
  "enabled": true,
  "anchor": "world | head | head-rigid | yaw-follow | position-follow",
  "pos": [0, -0.4, -0.75], "face": [0, 0],
  "pin": {"anchor": "yaw-follow", "rel": [12 floats]},
  "scale": 1.0, "active_opacity": 1.0, "idle_opacity": 1.0,
  "attention": {"enabled": true, "in_ms": 150, "out_ms": 250, "dwell_ms": 80, "hold_ms": 400},
  "follow_deadzone": {"enabled": false, "degrees": 15, "metres": 0.15},
  "pinned_apps": [],
  "groups": {"left": [...], "center": [...], "right": [...]}
}
"screens": [{..., "dock": {"docked": true, "slot": 0}}]
```

`anchor: "screen"` (older layouts) places the toolbar under screen N once; enabling it converts that to a world pose.

Opacity defaults to 1.0 both looked-at and idle; lower it in Display Settings → Toolbar.

Profiles: `ft-layout profile save` stores the whole sanitized `toolbar` object (pose, follow, look, modules, pinned apps) next to the screens and instruments, and applying the profile restores it. Profiles saved before this have no `toolbar` key and leave the current toolbar as it is.

Socket (`@ft_screens`):

- `toolbar enable|disable|clear|module SIDE TYPE [ARG]|place X Y Z YAW 0 0|recenter|pin MODE [rel×12]|opacity A [I]|attention on [in out dwell hold]|off|deadzone on [deg m]|off|scale S|attach screen N|get|state`
- Module TYPE: `start|tasks|displays|tray|home|launcher [ID]|profiles|action NAME|user`
- Taskbar: `toolbar taskbar` (state), `toolbar open KIND` (same as pressing its button), `toolbar overlays` (diagnostic: every visible Frametop overlay that takes laser input, with key, alpha, width × hit height in metres and world y — finds invisible hit areas); from ft-taskbar: `toolbar popup KIND SERIAL`, `toolbar popup-close KIND`, `toolbar tasks SERIAL`, `toolbar tray volume LEVEL PCT`, `toolbar tray wifi ENABLED BARS CONNECTED`
- `dock N on [SLOT]|off|toggle`, `dock state`

CLI: `ft-layout toolbar state|enable|disable|recenter|capture|follow|opacity|scale|attention|deadzone|pin-app|unpin-app`, `ft-layout dock N on|off|toggle|sync|state`.

Display Settings → **Toolbar** page edits all of it (see [FT_DISPLAY_SETTINGS.md](FT_DISPLAY_SETTINGS.md)).

## Related

[SCREENS_VR.md](SCREENS_VR.md), [FT_LAYOUT.md](FT_LAYOUT.md), `docs/reference.md`

## Tests

```
python3 test/test_desktop_toolbar.py
python3 test/test_toolbar_dock.py
python3 test/test_taskbar_model.py
python3 test/test_chrome_layout.py     # screen chrome row (no profile slots)
bash test/_toolbar_overlays.sh         # live: `toolbar overlays` reply (no restart)
bash test/_overlay_hit_probe.sh        # live: SteamVR's view of every toolbar / screen overlay (vrprobe)
bash test/_overlay_hit_scan.sh [KEY…]  # live: measured laser hit area per overlay (vrprobe --scan)
bash test/_overlay_aspect_probe.sh     # SteamVR hit aspect: default vs texture-sized mouse scale
bash test/_deploy_taskbar_dock.sh      # live: deploy + dock / undock round trip on the Frame
bash test/_deploy_taskbar.sh           # live: deploy + taskbar / popup checks
bash test/_taskbar_task_live.sh        # live: one app appears as a task, then closes
bash test/_ds_toolbar_smoke.sh         # Display Settings Toolbar page, offscreen, throwaway HOME
```
