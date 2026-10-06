# Frametop design

Why Frametop is built the way it is, and what we learned about SteamVR on the Steam Frame while building it. [reference.md](reference.md) describes the parts and how to run them. Read the SteamVR notes here before changing how the screens, the pointer, or the input relay talk to SteamVR.

## Goals

- Several desktop screens in SteamVR, each a real monitor with its own resolution and shape, placed anywhere around you.
- One physical mouse that drives a cursor through that 3D arrangement, and through the rest of SteamVR too: the dashboard, Steam, and other overlays.
- Controllers stay fully usable, and VR games aren't disturbed.
- Everything runs on the Frame itself, installed from a terminal on the headset.

## Screens and Spatial Instruments

Screens are application/content surfaces (nested KWin outputs in SteamVR).

**Spatial Instruments** are lightweight ambient information that exists directly in VR space rather than inside a virtual display. They reuse the same anchor/follow, soft-follow dead zone, true eye-gaze attention opacity, and shared visibility / VR-game hide rules as screens, but they are not Wayland surfaces and do not drive the desktop pointer.

Current types:

- **Clock** — transparent floating `HH:MM` (24-hour local time). Colour is configurable (`#RRGGBB`).
- **Date** — ambient `TUE 29 SEP` style (weekday abbr + day-of-month + month abbr). Refreshes once per local calendar day. Colour is configurable.
- **Battery** — five-segment ambient gauge for the Steam Frame headset battery (no percentage text). Reads `/sys/class/power_supply` (prefers `max1720x*` Battery nodes; polls every ~20s). Colour is configurable.
- **Device storage** — one fill bar for internal storage. SteamOS splits the SSD across several mounts (`/`, `/var`, `/home`, …); Frametop sums unique `/dev/sd*` (and similar) filesystems by device node so bind mounts of `/home` are not double-counted. Polls `/proc/mounts` + `statvfs` about every 30s (inside the distrobox it prefers `/run/host…` mounts).
- **SD card** — fill bar for `mmcblk*` media. If the card is inserted but not mounted, capacity still comes from `/sys/block/mmcblk*/size` (used = 0, soft “present” stripe).
- **Media** — scrolling now-playing label plus prev / play-pause / next glyphs (no filled transport bar behind them). MPRIS players live on the nested Plasma session bus; `session/ft-mpris.py` (started inside `dbus-run-session` by `frametop-session.sh`) exposes them on the abstract datagram socket `@frametop_mpris`. `ft-screens` (in distrobox) polls that socket and makes the Media overlay interactive so controller lasers can click the transport buttons (OpenVR mouse is bottom-left; hit tests flip Y). Colour is configurable. SoftOutline and the old opaque control strip are skipped on Media to avoid marquee flicker.
- **Launcher** — multi-instance spatial shortcut (`launcher`, `launcher-2`, …). Action (independent of look): Application (`.desktop` id), Frametop/Asterism semantic action (`profile.slot.N`, …), or expert Custom Command (argv or explicit `/bin/sh -c`). Appearance: app icon (default; SVG theme icons are rasterized to PNG under `~/.config/frametop-instruments/`), built-in glyph, custom image, or fallback star. Floating icon only — no tile. Gaze attention only; deliberate content click activates via `@frametop_launch` (`session/ft-launch.py`). Activations always load `plasmashell.env` (nested `wayland-N`) so apps open on the existing Frametop displays — not as extra ft-screens overlays. Move bar moves; icon click launches. Profiles **replace** the full instruments list (including Launchers); old profiles without `instruments` clear them.
- **Image** — floating PNG/JPEG/GIF with alpha. Display Settings (or `ft-layout instrument file image[-N] PATH`) copies into `~/.config/frametop-instruments/{id}.*`. Ids `image`, `image-2`, … (`type` stays `image`). `ft-screens` loads via stb_image into an RGBA overlay (`SetOverlayRaw`). Caps: long edge 768, ≤48 frames, ≤48MB decoded.

Instrument move bars stay shown (transparent) while the instrument is visible — same laser-hit policy as screen chrome — with a larger proximity volume over the face and bar. Colours default to CRT green (`#39FF14`) with phosphor amber / magenta / cyan presets.

Configure them under Display Settings → Spatial Instruments. Profiles capture each instrument’s state with the screens. Charging animation / remaining-time estimates / byte captions are deliberately out of scope for V1.

### Why our own compositor

SteamOS already shows a single-screen Plasma desktop in VR by running KWin nested inside gamescope. The first version of Frametop did the same with gamescope's `PerWindow` mode and `kwin --output-count N`, which gives each KWin output its own SteamVR overlay. It worked, but gamescope has two limits that ruled it out:

- It draws every window into one shared canvas of a single size, letterboxed, and never tells a window what size to be. So every screen had the same resolution and shape; portrait screens had to be rotated outputs on rolled panels.
- Its OpenVR backend allocates an upload buffer of exactly 1920 × 1080 × 4 bytes, so anything larger, such as 3440 × 1440, aborts it at start.

It also leaves the panels to SteamVR's dashboard, which places them and doesn't expose their position to other programs.

ft-screens replaces it. It's a small wlroots compositor that hosts the nested KWin. KWin's nested Wayland backend opens one window per output and resizes an output when the host configures its window, so ft-screens can give each screen any size, live. KWin needs `wl_compositor` v4 or later, `wl_shm`, `wl_seat`, `xdg_wm_base`, and `zwp_linux_dmabuf_v1` v4 with feedback from its host; the rest is optional.

Frames go to SteamVR the same way gamescope sends them: OpenVR's `IVRIPCResourceManagerClient` imports each DMA-BUF (`ImportDmabuf`), and the overlay shows it as a `TextureType_SharedTextureHandle` texture. There's no copy and no size limit. The Frame's SteamVR supports this interface, but the OpenVR header bundled with SteamVR's samples predates it, so the build fetches a pinned header from Valve's openvr repository.

Before settling on this, we tried KWin's screencast virtual outputs. KWin 6.2.5 crashed (`std::out_of_range` in `textureForOutput`) streaming one while nested in gamescope, and its headless backend doesn't implement virtual outputs at all.

A few wlroots details worth knowing: `wlr_shm_create` wants DRM format codes, not `wl_shm` ones, and KWin asks for server-side decorations before its first commit, when setting the mode would assert, so ft-screens answers on the first commit.

### Placing and sizing

Because the overlays are ours, ft-screens places them exactly with `SetOverlayTransformAbsolute` and draws its own controls under each screen. OpenVR has no overlay-relative transforms, so the controls are repositioned whenever their screen moves.

The curved layout chains screens edge to edge, like monitors on a desk: the middle screen (or the seam between two) straight ahead, and each neighbour hinged at the previous screen's outer edge and turned to face you. An earlier version spaced screens by angle, which assumes every screen sits on the circle; a flat 3.6 m screen's edges are much farther away than its centre, so its neighbours landed in front of it. Solving for the hinge angle needs a scan and bisection, because a simple fixed-point iteration diverges for screens nearly as wide as twice their distance.

`SetOverlayCurvature` takes the fraction of a full cylinder that the overlay's width covers, so the radius is width / (2π × curvature). The stated width is the arc length, and the cylinder bends toward the viewer: at a 2 m radius, a 3.57 m wide screen's corners sit about 75 cm closer to you and 23 cm further in than a flat screen's would. Controls on a curved screen are placed on that cylinder, and the bar gets the same curvature.

A resize handle has to be able to shrink a screen from any direction, so the dragged corner follows the laser along the screen's diagonal rather than taking the larger of its horizontal and vertical reach. Pushing and pulling a carried screen moves it along the line from your head, because the 3D mouse's virtual controller sits just in front of the bar, below the screen's centre, so the line from the device points mostly upward.

Wherever ft-screens needs to know where a laser points (showing the controls, the resize tab, the roll knob), it uses the laser's own pose, the render model's `tip` component, rather than the controller's pose. On the Frame's controllers the tip points 40° below the pose's forward axis, so rays from the pose missed what the laser was actually on. The 3D mouse's virtual controller has no tip, and its laser runs along its pose.

`ComputeOverlayIntersection` ignores `SetOverlayIntersectionMask`, and a control can't be allowed to cover part of its screen, so the resize tab sits entirely outside the corner.

### Wrist pinning

Pinning started as "bring the screen to your wrist", which doesn't work for big screens, because their centre is far from the edge you bring close. It became aiming: while a screen is carried, the line from the carrying device to its bar is tested against the other hand controllers. Crossing a controller's 6 cm ring arms the pin (leaving past 9 cm, so it doesn't flicker), and crossing it again disarms it. The pin happens on release, with the screen's pose at that moment, so you can arm it and then turn the screen. An earlier version pinned the moment the laser touched the wrist, which left the screen at whatever angle the carrying hand had while pointing there.

A pinned screen's alpha follows the angle between its front and the direction to your head, fully visible inside the wrist angle and fading over the last 10°. That fade applies only to controller (wrist) pins.

### Follow modes (anchors)

Each screen has one `AnchorMode`: world, left/right controller, head (soft), head-rigid, yaw-follow, or position-follow. Soft modes (`head`, `yaw-follow`, `position-follow`) keep an absolute overlay pose and chase a reference frame at the VR update rate with exponential smoothing (`FOLLOW_LAG_MS`, default 120). Head-rigid and controller pins still use `SetOverlayTransformTrackedDeviceRelative` with no lag. Legacy profile pins with `"hand": "head"` mean soft head.

Composed overlay alpha is a single path: `attentionResolved × visibilityFade` (wrist fade is visibilityFade). Each screen stores `activeOpacity` / `idleOpacity` (looking is never allowed to be dimmer than idle — swapped values are corrected). With attention off, `attentionResolved` tracks active (legacy single `opacity` maps to both, attention off). With true-eye attention on, gaze on that screen or its chrome dwells then smooths toward active; leaving smooths toward idle. Soft-follow freezes under gaze only for head-soft: that mode would otherwise pitch/slide the surface while you read. Yaw-follow and position-follow keep chasing while focused — freezing them caused path stutter when eye samples flickered on/off the panel. Position-follow always applies a small (~2.5 cm) lock floor so millimetre HMD noise does not jitter a still sitter; user deadzone distance is clamped to at least that floor. Brief OpenVR eye-sample dropouts reuse the last ray for ~450 ms (`g_eyeHeld`); only after that grace (and the screen’s `attentionHoldMs`, default 400 ms) does opacity ease toward idle. Head forward is never a silent substitute for eye gaze.

**Dashboard / Steam UI layering.** Frametop panels are OpenVR `Basic` overlays from an overlay app. SteamVR’s dashboard and many streamed Steam UIs do not share reliable cross-app depth with them — a farther Frametop screen can still paint over nearer Steam UI. Chrome used to use `SetOverlaySortOrder(10)`, which made that worse. Chrome is now sort 1 (0 while the dashboard is open); screens and instruments stay at 0. While `IsDashboardVisible()` and eye gaze is available, Frametop **yields**: panels the user is not looking at (and not dragging / laser-hovering) are hidden so Steam can own the foreground; look back at a Frametop panel to bring it up. Without eye tracking, only the sort-order change applies (idle opacity still lets Steam show through when you look away).

Eye tracking uses OpenVR `IVRInput` with an `eyetracking` action (`screens/actions.json` → `/actions/frametop/in/EyeGaze`), bound via `bindings_frame_hmd.json` to `/user/head/eyetracking` (SteamVR's `CreateEyeTrackingComponent` name is `/eyetracking` on the HMD). Those binding files must sit beside `actions.json` when `SetActionManifestPath` runs, or vrserver logs `has no configured binding` and gaze stays empty. `GetEyeTrackingDataRelativeToNow` (then `…ForNextFrame`) supplies origin/target; hit-testing reuses screen-plane math against the **rendered** pose (same as soft follow). Closest screen/chrome `GazeTarget` wins; Spatial Instruments are considered only when the ray misses every screen and its chrome, so a floating clock/battery/storage cannot steal display attention or the gaze reticle. Gaze only focuses (attention fade); it does not reveal bottom chrome — that stays laser / 3D-mouse for now. Head-direction fallback is an explicit `gaze fallback head` debug mode only. Opacity fade timings live in Display Settings (`attention.in_ms` / `attention.out_ms`), not under-monitor chrome.

VR chrome: thin horizontal opacity strip above the bottom button row, then drag / curve / roll / resize / anchor cycle (world → head-soft → yaw-follow → position-follow; head-rigid stays CLI/settings), and a **dock to dashbar** control. Profile slots live on the spatial toolbar's Displays popup, not under each screen. The **desktop toolbar** (Start / Tasks / Displays / Tray; `desktop_toolbar.inc`, host `ft-taskbar`) is Frametop-owned SteamVR ControlBar-shaped chrome — on by default for 0.1.0 — and yields with the dashboard like the screens; it does not inject into Valve's dashboard. SteamVR's digital keyboard is not wired into chrome for now. Aurora / camera passthrough has no public OpenVR toggle for overlay apps. Slot clicks spawn `ft-layout action profile.slot.N` asynchronously. Input Settings and Display Settings share the same semantic action names. Soft follow seeds from the current rendered transform when a mode is applied so pinning after a profile transition does not pop. Optional per-screen **follow dead zone** (Display Settings): small head turns / steps leave a locked reference so you can glance at a panel corner; past the threshold the lock is pushed by the excess only (head / yaw-follow use degrees; position-follow uses metres).

### Visibility and VR games

`VROverlayFlags_MakeOverlaysInteractiveIfVisible` keeps SteamVR's laser mouse on while an overlay with that flag is visible. Without it, the laser is off whenever the dashboard is closed: the first click on a panel only turns it on, and the laser turns off again as soon as it leaves every panel. With it, controllers work the screens normally, but the laser also takes the controllers away from a VR game.

Pointer hits from OpenVR are in DMA-BUF buffer pixels (`SetOverlayMouseScale`). Nested KWin often attaches the window with integer `buffer_scale = ceil(output_scale)` (e.g. surface half of buffer at 125%) while Qt uses the *output* scale as devicePixelRatio. `screens/coords.h` (`ft_buffer_to_seat`) maps buffer → seat with that in mind: when wl dpr and output scale diverge, seat = buffer / output_scale; otherwise buffer → surface. `ft-layout scale` pushes each screen’s output scale into **vr.cpp** (`scale N F`); the compositor forwards that command and must not divide pointer coords again (upstream’s simpler compositor-only divide conflicts with this path). Preferred `wp_fractional_scale` follows the same factor. Changing UI scale must not change the panel width in metres. Gaze `pixel=` uses the same seat mapping.

`IVRApplications::GetCurrentSceneProcessId()` is 0 when no VR scene app is running (the Frame's home environment isn't a scene app) and the game's process ID while one is. Flatscreen games use `valve.steam.desktopgame[.N]` overlays instead. ft-screens maps both (plus Steam's Enter gamepad mode, which `hideDashboard`s and often hides the theater overlay) into one `AppActivity` (~2 Hz, `screens/app_activity.h`): display hide and OutsideGames laser ownership follow that, so Frametop does not reappear and steal controllers mid-transition. A leftover registered `desktopgame` key after exit does not count unless the overlay was seen visible (latch).

## The 3D mouse

The mouse works like the pointer on the Apple Vision Pro: a small cursor floats in the room, lands on whatever panel it meets, and acts on it like a controller's laser.

### A virtual controller

SteamVR's dashboard and every overlay it hosts are driven by the vrcompositor `lasermouse` action set: a pointer pose, left, right, and middle click, back, home, scrolling, and a system button that toggles the dashboard. So the 3D mouse is a virtual controller. The `ft_pointer` driver adds an invisible controller (its render model is a single transparent triangle) with its own controller type and default bindings for vrcompositor and the Steam client. Its `/input/a` button is bound to `lasermouse_secondary/switchlaserhand`, which moves the laser to it without clicking. `/pose/tip` didn't work for the laser, because tip is defined by a render model; `/pose/raw` does.

Driver poses are in SteamVR's raw tracking space, and client programs work in the standing universe, which on the Frame is about 1.6 m above raw. Mixing them up put the laser's origin 1.6 m above your head. The helper converts using the headset's pose in both spaces every frame.

Frametop's SteamVR clients (ft-pointer, ft-screens) connect as a background app first and switch to an overlay app only once that works. `VR_Init` as an overlay app starts vrserver itself when none is running, and one started that way from the dev container never finds the headset. At a boot where the gamescope session timed out, systemd dropped `steamvr.service`'s start job, the pointer service (ordered only `After=` it) started anyway, and its vrserver made every SteamVR launch fail with `HmdNotFound`. SteamOS's health check then kept resetting the Steam client and tried to fall back to the previous OS slot. The units also say `Requisite=steamvr.service`, so they don't start at all when SteamVR's start fails. They deliberately do **not** use `Requires=`: FrameTop clients stay disposable and must never block SteamVR itself.

The driver starts disconnected, because holding the right-hand role while SteamVR starts leaves the Steam UI stuck on its loading icon. It connects when the mouse is used and claims the right hand. SteamVR keeps a hand role reserved for a disconnected device that still asks for it, so the driver switches its role hint between right hand (connected) and opt-out (not connected).

### The cursor

Mouse motion turns into yaw and pitch around an anchor, the head position at the last recenter. A ray from the anchor is tested against every visible overlay with `ComputeOverlayIntersection`. On a hit, the cursor sits on that surface; otherwise it floats at `POINTER_DISTANCE`. Since the anchor isn't your current eye position, a second test runs along your line of sight to the cursor point, and anything nearer wins, so the cursor always lands on what you see under it.

OpenVR has no call to list other programs' overlays, so the helper runs `vrcmd --overlays` in the background. It includes hidden overlays, because a floating window's controls only appear while something hovers the window, and the cursor has to find them immediately.

The laser starts partway along your line of sight to the cursor rather than at your eye. SteamVR sizes its hit dot by distance from the laser's origin, and a laser from the eye still shows a beam in each eye. Starting it close to the target makes the beam and the dot tiny, while `POINTER_ORIGIN_MARGIN` keeps the origin in front of the small window controls, which float a few centimetres in front of their panels. The helper's own white dot is the visible cursor. In empty space it's an interactive overlay that the laser lands on, so SteamVR never draws a laser into nothing.

A few overlays need special handling:

- The dashboard's dock and the floating windows' controls are scene-graph overlays with no texture (0 × 0) and a placeholder width, so `ComputeOverlayIntersection` never hits them. For those the helper tests the overlay's plane within `POINTER_SCENE_RADIUS` of its origin.
- SteamVR's Settings page is the one page `ComputeOverlayIntersection` can't find. Steam's pages, Library and the rest, are drawn in `valve.steam.gamepadui.main`, which it hits exactly. For SteamVR Settings that overlay is hidden, and the page is drawn by the dashboard's scene-graph panel, whose shape OpenVR doesn't give out, and whose transform's plane isn't the page's surface. The laser started behind the page, so most of it took no clicks (they went to a desktop screen behind it), and the page covered the dot. On that page only, the laser now starts near the eye so SteamVR's own hit test finds the page, the dot is drawn close in front of it, and the laser-catching dot sits far behind everything, invisible, with SteamVR's hit dot hidden on it. There the beam and SteamVR's hit dot look like a controller's; everywhere else nothing changes.
- Just off a panel, the cursor stays on that panel's plane within `POINTER_EDGE_REACH`, so resize margins and window controls just outside the panel are reachable.
- While the left button is held, the cursor keeps the distance it had at the press and stops re-testing collisions, so dragging past a panel's edge doesn't make it jump.

Head follow is experimental and off by default. It works, but it's only lightly tested, and the feel is mostly a matter of its settings; polishing it is left open. With it on (`POINTER_FOLLOW=1`, or a mouse button mapped to Head follow on/off), the cursor rides on a reference direction, where you were facing when your head last settled, and keeps its offset from it. The mouse can put the cursor anywhere up to `POINTER_FOLLOW_REACH` (70 degrees) from the reference, a corner of your view included. While your head stays within `POINTER_LEASH_DEG` of the reference, nothing moves on its own. Once your head has been past the leash for `POINTER_LEASH_DELAY` (0.2 s, so a glance out and back doesn't count), the reference eases to where you're facing (time constant `POINTER_LEASH_RETURN`, 0.2 s), never falling further behind than the leash, and the cursor ends up back where it was in your view. Then it waits for the leash again. Two earlier versions didn't work out. Moving the reference only while your head pulled at the end of the leash left it up to the leash off after you turned back, and getting it centred again meant overshooting with your head. Easing it toward your facing all the time moved the cursor on every small head movement. A leash of 0 makes the reference your facing direction, so the cursor is locked to your view, and mouse movement shifts it within the view. Head roll is ignored, so tilting your head doesn't swing the cursor around. While the left button is held the cursor stays put in the room, so your head can't nudge a click or a drag. When you let go, it carries on from where it is instead of jumping.

Replacing a loaded driver's files, as re-running the installer used to do, leaves SteamVR honoring the virtual controller's hand role but not its laser claim: the dashboard pointer stays unassigned until SteamVR restarts. The driver installer now leaves an unchanged driver in place.

`dashboard.laserRayWidthScale` controls the beam's width, but SteamVR only applies a change from its own settings screen or at restart, so it can't be switched per device while running.

### Handing the laser back and forth

The dashboard follows whichever device summoned it or last pressed its trigger. Frametop adds "last used wins": moving a real controller releases the pointer, and the next mouse movement takes the laser back. Moving means faster than 0.35 m/s or 2 rad/s (both times `POINTER_CONTROLLER_PICKUP`, 1 by default) for 100 ms in a row, while the controller is tracked normally. A single sample over the limit used to be enough, and controllers resting on a desk took the laser back on a knock or a tracking jump while the mouse was in use. Small movements don't count; waking needs `POINTER_WAKE_COUNTS` of mouse motion within a second, so desk jitter doesn't steal the laser. While the pointer is awake, a tiny transparent overlay with `MakeOverlaysInteractiveIfVisible` keeps SteamVR's laser mouse on, since otherwise the first click would only switch the laser on.

When the headset comes off, SteamVR reports its activity level as idle at once and turns the displays off 5 seconds later (`power.turnOffScreensTimeout`), unless something keeps it awake. An awake pointer did, and so did the helper's `vrcmd` runs: each is a new SteamVR client, and a new client every second kept SteamVR out of standby. The helper now releases the pointer as soon as the headset is idle, ignores the mouse until you're wearing it again, and pauses the overlay list whenever the pointer is off.

### Moving floating windows

For SteamVR's own floating windows, the dashboard does the moving. A press on a window's grab bar, 7.5 cm below its bottom edge, parents the window to the pressing device with the relative transform at the press. The scroll wheel pushes it along its normal in steps of about 7 cm. The dashboard finishes the move up to 150 ms after the release and reads the device's pose again then, so the helper holds the drag pose for half a second after the button comes up. Tilting works by rotating the virtual controller around the grab point while both buttons are held.

## Input relay

SteamVR opens every input device only when it starts. When a Bluetooth mouse sleeps and reconnects, it gets new device nodes, and SteamVR keeps holding the old, deleted ones, so the mouse stops working until SteamVR restarts. The relay creates permanent virtual devices through uinput before SteamVR starts and forwards the real devices' events into them. systemd keeps the virtual devices' file descriptors across relay restarts, so SteamVR never sees them disappear.

Keyboards aren't grabbed by default, because a grabbed keyboard's keys went into a virtual keyboard nothing typed from; the relay forwards them to ft-screens instead.

The control socket (`@frametop_relay`) is an abstract Unix datagram socket with no permissions, so any local process can send to it. One malformed datagram used to unwind through `handle_control` and kill the whole relay (for example `watch abc` → `float("abc")`). That drops every grab, including the volume-key takeover that keeps gamescope from aborting. Dispatch of each datagram is now wrapped so a bad message is logged and skipped while later ones still run.

The relay also remembers which keys it told ft-screens went down (`screens_down`). Once a second it compares that set to the kernel's current key state (`EVIOCGKEY`) across every open node and releases any key the desktop still has down that no physical device holds. That recovers from a vanished Bluetooth keyboard mid-press, a lost release event, or a relay restart that left Meta/Ctrl/Alt/Shift stuck in Plasma. On startup it also proactively releases those modifiers on the desktop.

An ungrabbed keyboard reaches both sides at once. In VR, gamescope reads every input device itself (the SteamOS build's `InputStealer`, libinput with udev hotplug, so new devices too) and types into its focused app, and ft-screens types the same keys into the desktop. So Space in the desktop also paused Spotify on the dashboard. Typing now follows the last click. ft-screens sees clicks on its own screens, from the mouse or a controller. A click anywhere else is only visible for the mouse: overlay apps get SteamVR's `OverlayFocusChanged` (which panel the laser is on) but no controller button events, so the pointer helper reports the panel under the dot on each left press. ft-screens tells the relay where typing goes every second, from an unbound socket so the relay's replies can't loop back into its control socket, and the relay grabs pass-through keyboards while it's the desktop. A grab waits until the keyboard has no key down, so no key stays held on either side, and the relay lets go if ft-screens stops reporting. A program that reads every keyboard for a hotkey (a dictation tool, say) loses a grabbed keyboard. Repeating the keys on another input device doesn't work: gamescope reads that device too, whether it's the relay's virtual keyboard or one created later, and every Space, typed or dictated, paused Spotify again. So with `SHARE_KEYS=1` the relay sends a grabbed keyboard's keys to `@frametop_keys` as datagrams (`key <code> <value> <device name>`). It's off by default, because the relay can't tell who is listening: abstract sockets have no permissions, and any local process that binds the name first gets every key typed into the desktop, passwords included. A listener should accept only its own user (`SO_PASSCRED`) and skip any keyboard of its own that the relay grabs too.

Volume keys must never reach gamescope. With the openvr backend, gamescope sends volume up and down to Steam by moving keyboard focus to Steam for the key and then back to the previously focused surface. When nothing had focus, the one it moves back to is null, and wlroots aborts on a null focus surface (`wlr_seat_keyboard_notify_enter: Assertion 'surface' failed`), which ends the whole VR session. Keyboard focus is often empty while you work in VR, so one press of the headset's volume button could take everything down. gamescope reads the headset's buttons and every keyboard itself (`InputStealer`), as do SteamVR's processes, so the relay has to stop volume keys at the device. Grabbing `gpio-keys` would also take the headset's click button, so the relay remaps the volume entries in each device's keymap (`EVIOCSKEYCODE`) and handles the stand-in codes itself. That fix covers every device at once, including keyboards that aren't grabbed.

The Frame controllers can be mapped like mouse buttons, but they aren't input devices on the host: they reach SteamVR over the headset's own radio, and no evdev or hidraw node exists for them. So only a SteamVR client can read them. Overlay apps normally get controller input only while they have input focus, which a background helper never has. SteamVR's experimental global action set priority (`steamvr/globalActionSetPriority`, "Enable global input from overlays") lets an overlay's action set receive input anyway, and takes the inputs it binds from the scene app. Binding every button would take them all from games, so the helper's action manifest puts each button in an action set of its own, and it activates only the sets of mapped buttons. The mapping itself stays in the relay, which does the action, so mice and controllers share one list of actions.

### The keyboard

Nothing in a headset types by itself, and SteamVR's own keyboard types into SteamVR's overlays, not into a nested Wayland desktop. So ft-screens draws a keyboard panel of its own and types through the seat of the focused screen, like the input relay's keys do. Knowing when to open it takes the desktop's help: an input method (`input/ft-textinput`, KWin's `--inputmethod`) is the one thing a Wayland compositor tells when a client turns text input on or off, and it reports only that, to the relay, which owns the policy (the `vr_keyboard` rule and the `keyboard_toggle` button) next to the rest of the input rules. Qt, GTK and Firefox use Wayland text input; Chromium, Electron and X11 apps don't, hence the button.

The gamescope session leaves `QT_IM_MODULE=xim`, `GTK_IM_MODULE=xim` and `XMODIFIERS` in the user environment, and with them Qt and GTK apps talk to an X input method and never use Wayland text input, so the session script unsets them with the Steam client's other variables.

The keyboard shares the Steam menu's space, so every 9 polls ft-screens looks at whether SteamVR's dashboard or Steam's keyboard overlay is up and moves the panel out of the way, then back to where it was (`g_steamInFront`, `g_keyboardAside`). It opens only with a head pose, since it is placed relative to the eyes. The pointer helper counts every `frametop.*` overlay as a real panel, because the keyboard's shared texture reports no size and the size check would drop it.

A screen can also be taken off the headset alone (`conceal`, `"hidden"` in the layout) without touching the window on it, for a desktop screen that is wanted for the apps on it but not in view. It's a separate flag from the visibility mode, so no mode or hotkey reveals it.

## The desktop session

The session is modeled on SteamOS's `steamos-nested-desktop` and runs beside it. It has its own runtime directory, config (`~/.config/frametop`), and state, so it never disturbs the stock desktop's layout or panels. It runs on a private D-Bus from `dbus-run-session`, which has two consequences. KDE only launches apps in systemd scopes when systemd is on the session bus, so everything started in the desktop lands in its systemd unit, and stopping the unit would kill all of it; `session/keep-apps.sh` moves those programs out first. And tools that need the real user bus, like podman and `distrobox-host-exec`, have to be pointed at it explicitly. Failed activations of `org.freedesktop.systemd1` on that private bus are expected and are not themselves the plasmashell crash.

### plasmashell crashes (wp_linux_drm_syncobj)

A reproducible vanilla-Frametop failure: `ft-screens` and `kwin_wayland` stay up while `plasmashell` dies after a Wayland protocol error on `wp_linux_drm_syncobj_manager_v1.get_surface` ("invalid arguments" / unknown object). Wallpaper-only outputs go black and the taskbar disappears; open app windows can survive because KWin is still compositing.

`KWIN_EXPLICIT_SYNC` is an old **X11/GLX** `GL_EXT_x11_sync_object` toggle documented for KWin. It does **not** control the Wayland `linux-drm-syncobj-v1` path used here, so Frametop does not set it as a mitigation. The failure matches known client/compositor races where a surface is destroyed or already has a syncobj when Mesa/Qt calls `get_surface` again. There is no safe, documented env switch to disable only that plasmashell path on current Plasma Wayland; root-cause fixes belong in Qt/Mesa/KWin versions on the Frame.

Mitigation in Frametop: `session/ft-shell-watch.sh` runs inside the same `dbus-run-session` as `startplasma-wayland`. After the first nested `plasmashell` appears, it snapshots that process's real `/proc/PID/environ` into `$XDG_RUNTIME_DIR/frametop/plasmashell.env` (must be `WAYLAND_DISPLAY=wayland-0` under `…/frametop`, not the outer `ft-screens-0` socket). Respawn and `./desktops.sh shell-restart` both launch from that file. Pre-Plasma outer env is never used as the restart recipe. Watchdog identity: `$XDG_RUNTIME_DIR/frametop/ft-shell-watch.pid`.

The VR launcher starts the session from the Steam client, and the client's environment came along: `LD_LIBRARY_PATH` pointing at Steam's own runtime, whose `libavcodec` has no H.264 decoder, so VLC in the desktop couldn't play most videos, plus the client's overlay and launch settings. The session script drops the client's variables before it starts anything. SteamOS's global Mesa settings (`/usr/share/deckard/mesavars.sh`) stay, and the gamescope session's Vulkan layer (`ENABLE_GAMESCOPE_WSI`) is only kept for the gamescope backend.

Steam, not systemd, suspends the Frame: after `system_idle_suspend_ac_sec` (an hour by default) without input on AC power, it logs `Switching to power state: k_ESystemPowerState_Sleep` and suspends, even while charging. It's a Steam setting (Settings → Power → When Plugged In and Idle → Sleep after), so the README recommends setting it to Never. SteamVR's standby, which turns the displays off when the headset comes off, is separate.

Flatpak apps need `XDG_DATA_DIRS` to include Flatpak's exports, or Plasma opens Discover instead of launching them, so the session sources `/etc/profile.d/flatpak.sh`.

A podman container's monitor process (conmon) stays in the cgroup of whatever started the container, and `distrobox enter` starts it on demand. When a Frametop service happened to start the `dev` container, stopping that service stopped the container and everything in it, including the desktop's compositor. `scripts/container-up.sh` starts the container in a systemd scope of its own before anything enters it.

Program names stay within 15 characters, because Linux truncates process names there and the scripts find programs with `pgrep -x` and `pkill -x`. That's why the prefix is `ft-`.

## Approaches we dropped

- WayVR, an existing Wayland desktop for VR. It built and connected to SteamVR on the Frame, but nothing showed in the headset. It has no bindings for the Frame's controllers, and its KDE screen capture needs `xdg-desktop-portal-kde`, which SteamOS doesn't ship.
- gamescope in `PerWindow` mode, for the reasons above. Frametop still supports it as `BACKEND=gamescope`. In that mode SteamVR's dashboard owns the panels, so `ft-layout` floats each one with `vrcmd --dock-overlay` and the pointer helper carries it into place with the virtual controller, hovering first and then sliding at 0.5 m/s, because the dashboard exaggerates fast movements.
- A capture pipeline from a headless KWin through KWin's screencast protocol. It's workable, but ft-screens gets the frames directly with less code.

## Open questions

- A head-locked screen, like a HUD.
- A controller button that shows the screens during a game. Games own the controllers, so this needs SteamVR input actions for ft-screens.
- Drawing KWin's cursor on the screens.
- Plasma can lose its panels when the number of screens goes down, because they're saved against a screen that no longer exists. Removing `plasma-org.kde.plasma.desktop-appletsrc` and `plasmashellrc` from `~/.config/frametop` brings the default panels back.
- Frame pacing and GPU cost with several busy screens haven't been measured.
