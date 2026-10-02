# Frametop reference

How each part of Frametop works, where its settings live, and the commands for running parts of it by hand. For why it's built this way, see [design.md](design.md).

## The desktop

From the headset, open Launch a program → Desktop. The installer replaces that launcher entry with Frametop's (`~/.local/share/applications/deckard-nested-desktop.desktop`), and `desktops.sh uninstall` gives the stock single-screen desktop back.

From a terminal, on the Frame or from a PC over SSH:

```
desktops.sh install        # the launcher's Desktop entry starts Frametop
desktops.sh uninstall      # back to the stock SteamOS desktop
desktops.sh start | stop | restart | status | log [lines]
```

`session/frametop-session.sh` runs the desktop. It starts ft-screens in the `dev` container (log: `/tmp/frametop-screens.log`), then KWin and Plasma on the host inside it. Inside the private `dbus-run-session` it also starts `session/ft-mpris.py` (log: `/tmp/frametop-mpris.log`) so the Media instrument can talk to MPRIS players over `@frametop_mpris`. Only one desktop runs at a time. `desktops.sh start` runs it in its own systemd unit, `frametop-desktop`. It keeps its Plasma config in `~/.config/frametop`, separate from the stock desktop's.

If `plasmashell` exits while KWin stays up (black wallpaper / missing taskbar), `session/ft-shell-watch.sh` restarts only the shell inside the same nested D-Bus session, using `$XDG_RUNTIME_DIR/frametop/plasmashell.env` captured from the first healthy shell (`WAYLAND_DISPLAY=wayland-0`, not the outer ft-screens socket). Log: `/tmp/frametop-plasmashell-watchdog.log`. Manual: `./desktops.sh shell-restart`.

When the VR launcher starts the desktop, it inherits the Steam client's environment. The session script drops the client's runtime from it (`LD_LIBRARY_PATH`, the `STEAM_*` settings, and the Steam overlay's Vulkan layer), so apps in the desktop use the system's libraries, including its video codecs, just as they would after a normal login.

Settings are in two files, and Frametop Display Settings edits both. The screens (resolution, width in metres, scale, curve, which one has the taskbar) and their layout are in `~/.config/frametop-layout.json`. The backend, remote desktop, and pointer settings are in `~/.config/frametop.conf`; `session/frametop.conf.example` lists every key.

Restarting the desktop closes its windows. Before the unit stops, `session/keep-apps.sh` moves every program started in the desktop into a systemd scope of its own, so background work such as servers, tmux, and builds keeps running. An app that shuts down its own helper processes when its window closes will still lose them; run that kind of work outside the desktop, for example as a systemd user service.

## ft-screens, the compositor

`screens/compositor.c` is a small wlroots 0.20 compositor that hosts the nested KWin, and `screens/vr.cpp` is its SteamVR side. `screens/build.sh` builds it; the installer runs that for you.

Each KWin window is one screen. ft-screens sets its size with an `xdg_toplevel` configure and KWin resizes the output to match, live. Frames arrive as DMA-BUFs and go to SteamVR through OpenVR's `IVRIPCResourceManagerClient::ImportDmabuf`, with no copy and no size limit.

Every screen is an overlay named `frametop.screen.N` with under-chrome controls:

- `.bar` moves the screen. Drag it with any laser or with the 3D mouse, whose right-drag tilts. Scrolling while you drag pushes the screen away or pulls it closer, along the line from your head.
- `.curve` bends the screen into a cylinder around you, using your current distance as the radius, or makes it flat again.
- `.roll` rolls the screen when you drag it sideways, like a knob. It snaps level within 2.5°, and scrolling on it turns 5° per notch.
- SteamVR Aurora / Room View (passthrough) has no public OpenVR toggle for overlay apps, so there is no Frametop chrome button for them. Custom 360° compositor backgrounds are a separate SteamVR setting (`steamvr.background` / `steamvr.environmentMode`); use `scripts/frame-background` on the Frame. SteamVR's digital on-screen keyboard is not exposed in Frametop chrome for now.
- `.resize`, the tab on the bottom right corner, sets the width. Screens go down to 15 cm wide.
- `.anchor` cycles world / head-soft / yaw-follow / position-follow; profile slot circles 1–6 sit on the left of the bar.

**Spatial Instruments** live outside the virtual displays as ambient overlays (not KDE windows). Display Settings → Spatial Instruments configures them. Types: **Clock** (`HH:MM`), **Date** (`TUE 29 SEP`), **Battery** (five-segment headset charge), **Device storage** (summed internal mounts), **SD card** (`mmcblk*`), **Media** (MPRIS now-playing + prev/play-pause/next via `@frametop_mpris`), **Image** (floating PNG/JPEG/GIF with alpha; multiple as `image`, `image-2`, …), and **Launcher** (floating spatial shortcut; multiple as `launcher`, `launcher-2`, … — Application / Frametop action / custom command; app icon by default; gaze highlights only; laser-click activates via `@frametop_launch` inside the nested Plasma session). Clock, Date, Battery, and Media support CRT/phosphor `#RRGGBB` colours (default CRT green `#39FF14`). Instruments reuse screen-style anchors, gaze attention opacity, and the same shared visibility rules as the displays. Aim a controller laser at an instrument (or its always-present move bar) to brighten chrome; Media transport and Launcher icons take content clicks (move bar stays for reposition). Layout/profile JSON may include an `instruments` array; Image/Launcher custom art uses `path` under `~/.config/frametop-instruments/`. Applying a profile **replaces** the instruments list. Older files without instruments still load.

The controls are sized from both the screen's width and its distance from you, follow the surface of a curved screen, and stay invisible until a laser or the 3D mouse's cursor lands on one or comes within about 1.5 times a button's size of it. While invisible they're still there, fully transparent, so SteamVR's laser can find them. They're translucent until a laser is on them, like SteamVR's own window controls.

To pin a screen to a wrist, carry it by its bar and sweep the laser across your other controller. A ring around that controller marks the target, and a dot shows where the laser passes. Crossing the ring arms the pin, and the ring and bar turn blue; crossing it again disarms it. When you let go while armed, the screen rides on that controller at the size, distance, and angle it had, so you can arm the pin first and then turn the screen the way you want. Grab a pinned screen's bar to adjust it; it goes back to the same wrist when you let go unless you disarm it. A pinned screen shows only while you're looking at its front, within the wrist angle, and fades out over the last 10°.

The Visibility tab of Frametop Display Settings decides when the screens show:

- Always. Meta+Shift+H, the Hide/Show Screens menu entry, or a mapped mouse button hides them.
- Only while the SteamVR dashboard is open.
- Hide whenever the SteamVR dashboard opens (`except_dashboard`): screens stay up normally, then hide so Steam UI has the view; Meta+Shift+H shows them anyway while the dashboard is open.
- While you look at a chosen controller (the wrist gesture).
- Only after you show them with the hotkey.

In dashboard / except_dashboard / gesture / toggle modes the hotkey can force-show (or, for except_dashboard with the dashboard closed, force-hide like Always). Two more settings on the same tab cover VR games, which ft-screens detects as SteamVR scene apps:

- During VR games, the Always mode hides the screens and Spatial Instruments unless the dashboard is open (the default), or leaves them up.
- Controllers on the screens. Visible screens can keep SteamVR's laser mouse on, so controllers work them with the dashboard closed, but that also takes the controllers away from a game. By default this is off while a VR game runs, and the 3D mouse or the dashboard works the screens. The other choices are always on, or only with the dashboard open, which also suits flatscreen games since they aren't scene apps.

Input from the lasers reaches KWin through ft-screens' own seat. OpenVR reports hits in DMA-BUF (buffer) pixels; ft-screens maps those through `screens/coords.h` (`ft_buffer_to_seat`) before `wlr_seat_pointer_notify_*`. When KWin's output scale (e.g. 125%) differs from the Wayland integer `buffer_scale`, seat coords use `buffer / output_scale`; otherwise buffer maps onto the committed surface size. The compositor must not divide by scale again — that was the scaled-display misalignment after merging upstream's simpler divide-in-compositor path with this mapping. `ft-layout` sends each screen's scale (`scale N s`) into vr.cpp whenever it applies scales. Keys come from the input relay, from pass-through keyboards and any key a pointer device passes through. Typing follows your last click: after a click on a screen it goes to the desktop, even with the SteamVR dashboard open, and after a mouse click on any other panel (the dashboard, Steam, an app like Spotify) it goes there instead. While it goes to the desktop, the relay grabs pass-through keyboards so gamescope, which reads every keyboard itself, doesn't type them into the Steam app too. A program that watches every keyboard for a hotkey loses a grabbed one; with `SHARE_KEYS=1` in `~/.config/frametop.conf`, their keys also go to `@frametop_keys` for it. That's off by default, since any local process that binds the name first would get everything typed into the desktop. Hidden screens don't take typing.

KWin's nested backend doesn't undo a screen's scale on pointer input; Frametop corrects that in vr.cpp as above. A scale changed only in Plasma's own display settings is put back to the Frametop layout's the next time `ft-layout` runs.

ft-screens listens for datagrams on the abstract socket `@ft_screens` (override with `--control NAME`) and replies to the sender:

```
place N x y z yaw pitch roll     width N metres          curve N radius|on|off
pin N|all left|right [matrix]    unpin N|all             size N w h
get N    screens    head    state    key code value    scale N s
toplevels    input N move|down|up|leave [x y [left|right|middle]]
visibility always|dashboard|except_dashboard|gesture|toggle    wrist degrees    gesture left|right degrees
hide | show | toggle    controllers always|outside_games|dashboard    ingames hide|visible
vrkeyboard show|hide|toggle|close
```

`vrkeyboard` is described under Input relay.

`ft-screens --no-vr` skips OpenVR entirely (no overlays, no relay contact) for a disposable nested desktop beside the live one; see `screens/test/headless.sh` and [SCREENS_TEST_HEADLESS.md](README/SCREENS_TEST_HEADLESS.md). Production defaults (`@ft_screens`, VR on) are unchanged.
## Input relay

SteamVR opens input devices only when it starts. A Bluetooth mouse that sleeps and reconnects gets new device nodes, SteamVR keeps reading the dead ones, and the mouse stops working until SteamVR restarts. `input/input-relay.py` avoids this. It creates two virtual devices, `frametop virtual mouse` and `frametop virtual keyboard`, through `/dev/uinput` before SteamVR starts. It then grabs USB and Bluetooth mice and keyboards as they come and go and forwards their events, so SteamVR only ever sees the virtual devices, which never go away.

It runs as the user service `frametop-input-relay.service`, ordered before `steamvr.service` (`Before=`, not `Requires=`), with `TimeoutStartSec=20` so a hung READY cannot block SteamVR forever. It is `WantedBy=steamvr.service` only (not `default.target`).

The relay also owns the volume keys, on every device that has them, the headset's buttons included. It changes the volume itself (`wpctl`, 5% a step, repeating while held), and nothing else sees a volume key, gamescope and SteamVR included: on devices with a keymap (the headset's `gpio-keys`, USB and Bluetooth keyboards) it remaps just the volume entries to unused codes (`KEY_MACRO29`, `KEY_MACRO30`), so the headset's click button and the other keys still work, and it grabs `pmic_resin`, which has only volume down. The keymaps go back when the relay stops. With `--no-grab` it leaves the volume keys alone.

```
desktops.sh relay install     # enable it (starts with the next reboot or SteamVR start)
desktops.sh relay status | log | uninstall
input/input-relay.py --no-grab   # try it without taking devices from SteamVR
scripts/recover-vr.sh [--yes]    # stop/disable relay+pointer, unregister ft_pointer
```

The first time, the relay has to start before SteamVR, so reboot or restart SteamVR after installing it. After that it's safe to restart on its own: systemd keeps the virtual devices open in its file descriptor store (`FileDescriptorStorePreserve=yes`), so SteamVR keeps the same devices.

### Frametop's keyboard

For a text field in the desktop, ft-screens can show its own keyboard panel (`screens/keyboard.cpp`, see [SCREENS_KEYBOARD.md](README/SCREENS_KEYBOARD.md)). The desktop's input method, `input/ft-textinput` ([FT_TEXTINPUT.md](README/FT_TEXTINPUT.md), started by KWin through `--inputmethod`), sends `textfield 1|0` to the relay, and the relay's `vr_keyboard` rule (`always`, `no_keyboard` (default), `button`, `never`) decides whether to send `vrkeyboard show|hide` on to ft-screens. `vr_keyboard_persist` (default on) keeps it open after focus is lost. The **Open/close keyboard** action (`keyboard_toggle`) sends `vrkeyboard toggle` from a mouse or controller button, for apps that don't report text fields. A keyboard that a program created through uinput doesn't count as a connected keyboard for `no_keyboard`. The keyboard steps aside while the Steam menu or Steam's keyboard is open.

`vrkeyboard close` also closes it, and `ft-layout apply` sends it.

## The 3D mouse

A mouse drives SteamVR the way a controller's laser does, but shows up as a small dot anchored in the room. It snaps onto panels and works on the dashboard, Steam, overlays, and the desktop. The OpenVR driver is **opt-in**: a normal `./install.sh` does not register `ft_pointer` (pass `--with-pointer`, or install later). A broken external driver can prevent SteamVR from finding the HMD; recover with `scripts/recover-vr.sh --yes`. Three pieces make it work:

- The input relay, in pointer mode (`POINTER=1`), sends mouse motion, clicks, and scrolling to the helper. A deliberate movement or a click wakes the pointer, and 30 seconds without mouse input releases it.
- The helper, `pointer/helper/ft-pointer`, runs in the `dev` container as `frametop-pointer.service` and starts with SteamVR (`After=steamvr`, `TimeoutStartSec=45`). It keeps the cursor, tests it against every visible overlay, draws the dot, and sends the driver an exact pose.
- The driver, `pointer/driver/` (`ft_pointer`), is loaded by SteamVR. It's an invisible virtual right-hand controller whose laser follows the cursor. `pointer/driver/install.sh` backs up `openvrpaths.vrpath` before `vrpathreg adddriver`.

Whichever device you used last wins. Picking up a controller hands the laser back at once, and moving the mouse takes it again. When the headset comes off, the pointer lets go, so the displays can sleep, and it stays off until you're wearing the headset again.

To move a floating panel, left-drag its grab bar. The scroll wheel pushes and pulls it while you drag. Hold the right button while dragging and move the mouse to tilt the panel around the grab point; the right press isn't sent as a click. The tilt stays for the rest of the drag, and releasing the left button drops the panel as it is. A mapped Toggle dashboard button (or a Meta tap) wakes the pointer if needed and holds the virtual system button for 0.12 s, because SteamVR ignores a press and release in the same instant.

```
pointer/driver/build.sh && pointer/driver/install.sh install   # then restart SteamVR
pointer/helper/build.sh && pointer/helper/run.sh install
pointer/helper/run.sh status | log | restart
pointer/driver/install.sh probe     # devices, hand roles, who owns the dashboard pointer
scripts/recover-vr.sh --yes        # if SteamVR black-screens after enabling the pointer
                                   # also clears an empty steamvr-pending.path (realpath: '')
```

The pointer settings are in `~/.config/frametop.conf`: `POINTER_SENSITIVITY`, `POINTER_IDLE`, `POINTER_WAKE_COUNTS`, `POINTER_CONTROLLER_PICKUP`, `POINTER_DISTANCE`, `POINTER_CURSOR_DEG`, `POINTER_ORIGIN_FRACTION`, `POINTER_ORIGIN_MARGIN`, `POINTER_SCENE_RADIUS`, `POINTER_EDGE_REACH`, `POINTER_LASER_WIDTH`, the head follow settings `POINTER_FOLLOW`, `POINTER_LEASH_DEG`, `POINTER_LEASH_DELAY`, `POINTER_LEASH_RETURN`, and `POINTER_FOLLOW_REACH`, and the gaze mode settings `POINTER_GAZE`, `POINTER_GAZE_RETAKE`, `POINTER_GAZE_NUDGE_MAX`, `POINTER_GAZE_HOLD`, and `POINTER_GAZE_SHOW`. The example config explains each. Frametop Input Settings changes them live; after editing the file by hand, restart the relay or the helper.

## Frametop Input Settings

A Kirigami app with a Python backend, in the Plasma menu under Settings. It runs in the `dev` container and talks to the relay over its control socket, `@frametop_relay`. It has eight pages (the two added after Controllers/Pointer are Keyboard and Ignored panels, described below the list):

- Devices lists every USB and Bluetooth mouse and keyboard, with a light that flashes when the device is used. Each device gets a role: 3D pointer (grabbed, drives the pointer; the default for anything with a mouse), Pass through (grabbed only while typing goes to the desktop; the default for keyboards, where a Meta tap toggles the dashboard if `META_DASHBOARD=1` is in `~/.config/frametop.conf`), or Ignore. A device is identified by its Bluetooth address, or its USB ids and name, so all of its input nodes share one role. Forget drops everything saved for a device.
- Buttons maps a pointer device's buttons. Choose Capture a button, press the button or key, then pick an action: a click, back, scroll, toggle dashboard, recenter, pointer on or off, head follow on or off, gaze pointer on or off, faster or slower, reset or hide/show screens, profile slot 1–6 / next / previous, pass the key through, or nothing. Devices with saved mappings are listed even while they're asleep.
- Controllers maps the Frame controllers' buttons (every button but the system button) to the same actions, except passing a key through. Capture a button and press it on a controller, or pick it from the list. The controllers aren't input devices on the host; only SteamVR sees them. So the pointer helper reads them with SteamVR input (`pointer/helper/vrbuttons.h`, `pointer/helper/actions/`) and sends presses to the relay (`vrbtn right/a 1`), which does the mapped action. The helper only takes the buttons that are mapped (the relay tells it with `vrbind`), at an overlay-global priority, and only while no game (scene application) runs, so games keep every button; with In games on (`controller_in_games`), a mapped button is taken from games too. That needs SteamVR's "Enable global input from overlays (Experimental)" setting (`steamvr/globalActionSetPriority`), which the page's Global input switch turns on and off. Mappings are saved as `controller_buttons` in `~/.config/frametop-input.json`.
- Pointer has a Head follow switch and sliders for the pointer settings, which apply immediately, and a Recenter button.
- Gaze has the gaze pointer switch (on now and from now on; a mapped button toggles it until the helper restarts), the gaze mode sliders, the gaze service's state (headset, samples per second, whether only one eye is tracked, the calibration, the nudges learned), and Calibrate (opens the gaze probe), Reload calibration, and Forget nudges.
- Bluetooth lists paired devices and has Apply Bluetooth fixes, which runs `/etc/steamframe/bt-fixups.sh` through `pkexec`. Pair new devices in Steam.

- Keyboard picks when Frametop's keyboard opens (`vr_keyboard`: always, only while no pass-through keyboard is connected, only with the button, never) and whether it stays open after focus is lost (`vr_keyboard_persist`). It lists the pass-through keyboards connected now (a program's uinput keyboard doesn't count).
- Ignored panels lists overlays the 3D mouse should skip (`POINTER_IGNORE` in `~/.config/frametop.conf`: comma-separated patterns matched like shell globs against the overlay key, without backslash escapes). Overlays that were seen are offered to add, and entries can be removed. The pointer helper reloads the list when it changes. Every `frametop.*` overlay is always a real panel, never ignored by the "no size" check.

Device rules are saved in `~/.config/frametop-input.json`. `input-settings/install.sh` installs the menu entry. Its launcher hands podman the real `XDG_RUNTIME_DIR` and user bus and gives the app the session's Wayland socket, because the desktop session runs on a private D-Bus and podman fails on it.

## Frametop Display Settings and ft-layout

When the desktop starts, its screens arrange themselves around where you're facing. You can move them by hand at any time and put them back with Meta+Shift+R, the Reset Screen Layout menu entry, Arrange now in the app, or a mouse button mapped to Reset desktop screen layout.

The desktop's own screen arrangement follows where the screens are around you, whatever their numbers: a screen you see to the left of another is to its left in Plasma too, so the pointer and dragged windows cross straight to it. Screens one above the other stack, and screens pinned to a wrist come last. It's updated at startup, after arranging or saving the layout, and half a second after you let go of a screen you moved. With the headset off there's no head pose to go by, and the arrangement stays as it was.

Frametop Display Settings has tabs for:

- Screens: add and remove screens, and set each one's resolution (presets from 1080p to 4K, ultrawide, super ultrawide, portrait, or custom), its width in VR (0.5 to 6 m), active/idle opacity (0–100%; looking is never dimmer than idle), optional true-eye gaze attention with fade-in and fade-out speeds (while the SteamVR dashboard is open and eye gaze works, Frametop hides panels you are not looking at so Steam/stream UI can sit in front; head-soft follow freezes while gaze-focused so reading does not slide the panel — yaw/position follow keep moving), its scale, whether it's curved, anchor/follow mode, and whether it has the taskbar. Resolution, width, curve, and opacity apply at once. Adding or removing a screen takes a desktop restart, which the app offers.
- Layout: a curve around you, with the screens hinged edge to edge like monitors on a desk and each turned to face you, or a flat wall. Both take rows, distance, gap, and height. Save current arrangement keeps the positions and sizes you set by hand instead. Named spatial profiles (same screen count; pose, metres, curve, anchors, active/idle opacity, attention) can be saved, applied (default 450 ms transition), and assigned to slots 1–6 for the VR chrome buttons. A preview shows the layout from above and from the front, and a switch turns auto-arrange at startup on or off.
- Visibility: the visibility, game, and controller settings described above, the wrist angle, and buttons to pin all screens to a wrist, soft head / yaw-follow / position-follow, or unpin them.
- Background: SteamVR’s passive skybox (Aurora procedural, stock Night Mountains / Aurora Sky, or a custom equirectangular image). Uses `scripts/frame-background` on the host; see [FRAME-BACKGROUND.md](README/FRAME-BACKGROUND.md). Open with `FT_DISPLAY_PAGE=background`.
- Spatial Instruments: grid of cards whose previews match ft-screens’ real draw path (seven-segment clock, pixel+segment date, five battery blocks, storage/SD bars, media transport). Enable on the card; **Configure…** opens a settings dialog. **Add Image** / **Add Launcher** at the top.

`layout/ft-layout` does the arranging. It's a Python script that uses only the standard library and runs on the host:

```
layout/ft-layout apply [--duration MS]   # arrange every screen (optional ease-in/out move)
                                         # still pushes visibility, instruments, and (with --wait) KWin
                                         # scales if the HMD pose is not ready yet
layout/ft-layout capture                 # save the current arrangement and sizes as the layout
layout/ft-layout plan                    # print the arrangement as JSON (no VR needed)
layout/ft-layout scale                   # per-screen scale, positions (as the screens are around you), and taskbar screen, to KWin
layout/ft-layout screen state --json     # per-screen anchor/opacity + slot info
layout/ft-layout gaze state              # eye tracking + GazeTarget (attention path in ft-screens)
layout/ft-layout gaze debug on|off
layout/ft-layout gaze fallback head|off  # explicit head fallback (debug only)
layout/ft-layout instrument list|state [--json]
layout/ft-layout instrument enable|disable|recenter clock|battery|…|image-N|launcher-N
layout/ft-layout instrument file image|image-N|launcher|launcher-N PATH
layout/ft-layout instrument add image|launcher
layout/ft-layout instrument remove image-N|launcher-N
layout/ft-layout instrument desktop launcher-N DESKTOP_ID
layout/ft-layout instrument semantic launcher-N ACTION
layout/ft-layout instrument command launcher-N [--shell] …
layout/ft-layout instrument appearance launcher-N app|glyph|image|fallback …
layout/ft-layout instrument activate launcher-N
layout/ft-layout apps list [--json] [--search Q]
layout/ft-layout toggle                  # hide or show all screens
layout/ft-layout pin N|all left|right|head|head-rigid|yaw-follow|position-follow
layout/ft-layout profile list [--json]
layout/ft-layout profile current [--json]
layout/ft-layout profile save NAME
layout/ft-layout profile apply NAME [--duration MS]   # default 450; 0 = instant
layout/ft-layout profile delete NAME
layout/ft-layout profile slot N NAME | unslot N | slots [--json]
layout/ft-layout profile apply-slot N [--duration MS]
layout/ft-layout profile next|previous [--duration MS]
layout/ft-layout action NAME [--duration MS]   # profile.slot.N | screens.toggle | …
layout/ft-layout action list [--json]
display-settings/install.sh # menu entries and the Meta+Shift+R and Meta+Shift+H shortcuts
```

Spatial Instruments (Clock, Date, Battery, Device storage, SD card, Media, Image, Launcher) are stored in the active layout's `instruments` array and in named profiles. Missing `instruments` means none (profile apply clears them). Unknown `type` values are skipped safely. Media needs `session/ft-mpris.py` (`@frametop_mpris`). Launcher needs `session/ft-launch.py` (`@frametop_launch`); each activation loads `plasmashell.env` so apps open on the existing nested displays (SVG app icons are rasterized into `~/.config/frametop-instruments/`). Image/Launcher custom art copies under the same instruments dir (`ft-layout instrument file …` / `appearance … image`).

The active layout is `~/.config/frametop-layout.json` (relative to your head when applied). Named profiles are `~/.config/frametop-layout-profiles.json` (includes optional `slots` 1–6). Soft head follow lag is `FOLLOW_LAG_MS` in `~/.config/frametop.conf` (default 120). `/tmp/frametop-layout.log` has the run from the last desktop start.

Gesture ideas for profile switching are noted in `docs/gestures-profiles.md` (not implemented; prefer chrome slots and Input Settings actions).

## Remote desktop over VNC

With `REMOTE=1` in the config (`desktops.sh remote on`), the desktop is also served over VNC, for RealVNC Viewer or macOS Screen Sharing. `desktops.sh remote info` prints the address and password.

It listens on port 5900 on the Frame's Tailscale address only, not the LAN, so it needs Tailscale on the Frame ([deck-tailscale](https://github.com/tailscale-dev/deck-tailscale)). VNC authentication has no encryption of its own, so viewers warn about it, but the tailnet encrypts the traffic. The password is in `~/.config/frametop-remote/vnc-password` and VNC limits it to 8 characters. To change it, delete that folder and restart the desktop.

No VNC server can capture KWin on SteamOS directly: `krfb` needs `xdg-desktop-portal-kde`, which SteamOS doesn't ship, and `wayvnc` only works with wlroots compositors. So `session/remote-desktop.sh` captures the desktop with KDE's `krdpserver --plasma` on `127.0.0.1:3390`, and `session/vnc-bridge.sh` runs TigerVNC's `Xvnc` on display `:20` with a full-screen FreeRDP client inside it and serves that. Both run in the `dev` container, and the extra hop adds a little latency.

With remote access on, the nested KWin runs with `KWIN_WAYLAND_NO_PERMISSION_CHECKS=1`, so any app in the Frametop desktop could capture its screen or inject input. This applies only to that desktop, not the stock one. Port 3389 is SteamOS's own `xrdp`, which starts a separate X11 session rather than showing the VR desktop.

## SteamVR compositor background (Frame)

The passive sky behind the dashboard is SteamVR’s own compositor environment, not SteamVR Home and not Frametop.

- **Aurora** (`environmentMode=1`): procedural shaders under `/opt/steamvr/resources/shaders/.../distort_geom_aurora_*`, with knobs `auroraPalette`, `auroraSpeed`, `auroraHeight`, `auroraLightShafts`, etc.
- **Image** (`environmentMode=0`): latlong/equirect PNG path in `steamvr.background`. Stock assets live in `/opt/steamvr/resources/backgrounds/` (`aurorasky.png` 4096×2048, `night_mountains.png` 8192×4096). The compositor logs `Loading background skybox texture async '…'` and reloads live when the setting changes.
- User settings: `~/.config/openvr/config/steamvr.vrsettings`. Optional dome projection: `backgroundUseDomeProjection`, `backgroundCameraHeight`, `backgroundDomeRadius`.

Steam Frame’s dashboard UI still has Environment Style Image/Aurora, but hides solid-color background presets (`VRHTML.IsSteamFrame()`). Custom paths work through settings. Helper: `scripts/frame-background` (see `docs/README/FRAME-BACKGROUND.md`).

## Limits

- A controller button can't show hidden screens; a mapped mouse or keyboard button can.
- KWin's cursor isn't drawn on the screens, because KWin draws it as a host cursor, which ft-screens doesn't render. The 3D mouse's dot and SteamVR's laser tip show where you're pointing. Gaze-pointer mode draws a cyan reticle and temporarily hides SteamVR's `system.pointer` / `system.cursor` (without changing their width). Aiming a controller at a panel ends gaze mode so the normal laser tip comes back.
- The old gamescope backend (`BACKEND=gamescope`) still works, but it gives every screen the same resolution, at most 1920×1080 pixels' worth, and arranging screens borrows the pointer for a few seconds.
