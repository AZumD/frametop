# Steam 2D → Tovakai routing (exploration)

Stage 3 experiment: keep Steam as the launcher, route the game window into
FrameTop's nested KWin instead of SteamVR flatscreen theater.

**Make-or-break:** Steam launches and tracks a normal game; the real window
appears inside nested KWin.

Do not ship the chooser UI until the routing primitive is proven.

## Architectural split

| Concern | Owner |
|---------|--------|
| Steam launch intercept, cancel/relaunch, launch-option wrap, VR classification, SteamVR flat-panel suppression | `steam-frame-nix` / Asterism (`steamFrame.uiPatches.patches`) |
| Nested session env, window placement, main-display assign, taskbar | Tovakai / FrameTop (`tovakai-game-run`, KWin helpers) |

Do **not** add a bespoke Steam CEF patch framework inside FrameTop.

---

## Phase 0 — live system (2026-10-05)

### Nested Plasma environment (reference for wrapper)

Captured on Frame while desktop was up (`/run/user/1000/frametop/plasmashell.env`):

| Variable | Value |
|----------|--------|
| `XDG_RUNTIME_DIR` | `/run/user/1000/frametop` |
| `WAYLAND_DISPLAY` | `wayland-0` |
| `DISPLAY` | `:2` |
| `XDG_SESSION_TYPE` | `wayland` |
| `DBUS_SESSION_BUS_ADDRESS` | private bus under `/tmp/dbus-…` (session `dbus-run-session`) |

`session/frametop-session.sh` sets `XDG_RUNTIME_DIR=$host_runtime/frametop` before
`dbus-run-session` / Plasma. `ft-shell-watch` writes `plasmashell.env` there.
`layout/ft_desktop.nested_launch_env()` (used by `ft-launch.py`) loads that file and
refuses launches unless `WAYLAND_DISPLAY` is `wayland-N` and runtime contains `frametop`.

**Wrapper implication:** Steam's process env has host `XDG_RUNTIME_DIR=/run/user/1000`.
A Steam-child wrapper must **not** call `ft_desktop.plasmashell_env_path()` against
Steam's environ blindly. Prefer an explicit path:

```text
${XDG_RUNTIME_DIR:-/run/user/$UID}/frametop/plasmashell.env
```

when Steam still has the host runtime, or read the live nested `plasmashell` environ.
Only override display/session keys (`WAYLAND_DISPLAY`, `DISPLAY`, `XDG_RUNTIME_DIR`,
`DBUS_SESSION_BUS_ADDRESS`, maybe `XDG_SESSION_TYPE`); leave Proton/Steam Runtime
variables intact. Then `exec "$@"`.

### Window / placement surface already in FrameTop

- Taskbar / KWin scripting: `session/ft-taskbar.py`, `test/_kwin_windows.sh`
- Output send: `kwin.window_op("send", ids, output)`
- Layout primary screen: `layout/ft_layout.py` → `"primary"` (1-based)

Phase 10 can assign to primary after the window exists; not needed for Phase 5 proof.

### steam-frame-nix on this Frame

Still installed / active:

- `steam-ui-patches.service` **running** (`injector.mjs` + patches JSON)
- `~/.local/state/steam-frame-nix/ui-patches/*.json` (state for pet / close button / frame-controls)
- Home Manager: `~/.config/home-manager` → `~/nix-config` with `steamFrame = { … }`
- Nix store still holds launcher-menu / VR-keyboard patches

Documented API: `steamFrame.uiPatches.patches` entries target `SharedJSContext` (or
SteamVR `systemui` on `:8087`). Idempotent evaluate every ~15s; `unpatch` on service
stop restores stock UI without restarting Steam.

**Precedent already live:** `SteamClient.Apps.LaunchNonSteamApp` is wrapped (debounce +
optional close menu) — visible as non-native JS in SharedJS. Same infrastructure should
host GameAction intercept patches.

Asterism's SharedJS CDP/preexec stack is a parallel injector for Bookend work; for
Steam-facing launch routing, prefer **steam-frame-nix uiPatches** per project boundary.

### SteamClient.Apps on live SharedJSContext (CDP :8080)

Present and usable:

- `RegisterForGameActionStart` / `End` / `TaskChange` / `ShowUI` / `ShowError` / `UserRequest`
- `CancelGameAction`, `ContinueGameAction`, `GetActiveGameActions`, `GetGameActionDetails`, `GetGameActionForApp`
- `RunGame`, `CancelLaunch`, `TerminateApp`, `RaiseWindowForGame`
- `SetAppLaunchOptions`, `GetLaunchOptionsForApp`
- `RegisterForAppDetails`, `GetCachedAppDetails`
- `LaunchNonSteamApp` (already sfui-wrapped)
- Compat: `SpecifyCompatTool`, `SpecifyCompatExperiment`, `ClearProton`

Native methods report `Function.length === 0` in JS (bindings); do not trust arity —
probe by call.

### Hades (1145360) metadata sample

- `strCompatToolName`: `proton_11-arm64`
- `strLaunchOptions`: `""` (empty user options today)
- `GetLaunchOptionsForApp` returns configs with **`bIsVRLaunchOption: 0`** (DirectX + Vulkan Deck)
- `RegisterForAppDetails` payload did **not** expose `vr_supported` / `vr_only` fields
  on this client build — prefer launch-option flags + action/source for classification

Good Phase 2/5 candidate: **Hades** (Proton, non-VR launch options, installed).

Other installed 2D-ish titles seen: Stranded with You, Desktop Mate, summertime saga remake, etc.

---

## Probe tooling (this repo)

| Script | Doc |
|--------|-----|
| `test/_probe_game_routing_phase0.sh` | [_PROBE_GAME_ROUTING_PHASE0.md](_PROBE_GAME_ROUTING_PHASE0.md) |
| `test/_probe_game_routing_apps_cdp.sh` | (Apps API dump) |
| `test/_probe_game_routing_observe.sh` | Arms observe-only `RegisterForGameActionStart` |
| `test/_dump_game_routing_probe.sh` | Dumps `window.__ftGameRouteProbe.log` |

Observe probe is **temporary CDP inject** (survives until SharedJS reload). Permanent
form belongs in `steamFrame.uiPatches.patches` with a matching `unpatch.js`.

### Manual next step (Phase 1 capture)

1. Ensure Frametop desktop is up and CDP is on `:8080`.
2. `bash test/_probe_game_routing_observe.sh` (re-arms if needed).
3. From SteamVR, launch **Hades** (or another non-VR 2D title) **once**, normally.
4. `bash test/_dump_game_routing_probe.sh` and save `/tmp/frametop-game-action-log.json`.

Do **not** Cancel yet — first launch must be stock so we see real `action` /
`launchSource` / `gameActionId` shapes.

---

## Phase 1 — observe Hades launch (2026-10-05)

Stock launch from SteamVR while observe probe armed. **No cancel.**

### SharedJS `RegisterForGameActionStart`

```json
{
  "gameActionId": 1,
  "gameId": "1145360",
  "action": "LaunchApp",
  "launchSource": 100,
  "appIdGuess": 1145360
}
```

`RegisterForGameActionEnd` fired ~7.8 s later for the same `gameActionId` (when
Steam marked LaunchApp **Completed**).

**Answer Q1:** Yes — `RegisterForGameActionStart` catches the SteamVR library
launch path for a normal 2D Proton game (`action === "LaunchApp"`,
`launchSource === 100`).

Notes:

- `gameId` arrived as the decimal app id string `"1145360"` (not a tagged
  GameID bitfield in this callback).
- `GetActiveGameActions()` during the Start callback returned `{}` / later `[]`;
  do not rely on it at Start for metadata.
- Console tasks after Start (same ActionID 1): `ShowLaunchOption` → user picked
  `"1"` (Vulkan) → cloud/stats/controller → `CreatingProcess` →
  `WaitingGameWindow` → `Completed`. Cancel-on-Start will skip the launch-option
  UI unless we re-drive it somehow — document for Phase 2/11.

### Process tree (Steam still owns launch)

```text
reaper SteamLaunch AppId=1145360
  → SteamLinuxRuntime_4-arm64 _v2-entry-point waitforexitandrun
    → Proton 11.0 (ARM64) waitforexitandrun Hades.exe …
      → wineserver + Hades.exe
```

Steam console: `Game process added : AppID 1145360 …`; while running,
`RegisterForAppDetails` → `eDisplayStatus: 4` (running). Overlay preload present
(`gameoverlayrenderer.so` in pressure-vessel `--ld-preload`).

### Display env of the running Proton game

| Variable | Game (host Steam path) | Nested Plasma |
|----------|------------------------|---------------|
| `DISPLAY` | `:1` | `:2` |
| `WAYLAND_DISPLAY` | *(unset on game procs)* | `wayland-0` |
| `XDG_RUNTIME_DIR` | `/run/user/1000` | `/run/user/1000/frametop` |

For Proton/Wine, **`DISPLAY` is the decisive redirect target** for Phase 3/5.
No `gamescope -f` wrapper on this Hades launch (unlike some other titles in the
same console log).

### FrameTop while Hades stock-presented

`ft-screens state` → `outside_games 0 hide` (desktop yielding to flat game);
toolbar `visible=0 dash_yield=1`. Expected stock SteamVR flatscreen behavior —
not nested KWin.

Helpers: `test/_probe_game_routing_live.sh`, `test/_probe_game_routing_running.sh`.

---

## Phase 2 — cancel → stock `RunGame` (2026-10-05)

Armed via `test/_arm_game_routing_phase2.sh` (Hades only). User launched once.

### Timeline (SharedJS log)

| t (relative) | Event |
|--------------|--------|
| 0 ms | `start` ActionID **2**, `LaunchApp`, source 100 |
| +1 ms | `CancelGameAction(2)` → `cancelOk: true` |
| +13 ms | task `ShowLaunchOption` (still on cancelled action) |
| +103 ms | `end` ActionID 2 — **no CreatingProcess** |
| +502 ms | `RunGame("1145360", "", -1, 100)` |
| +559 ms | `start` ActionID **3**, `bypass: true` → bypass consumed |
| … | normal tasks through `CreatingProcess` → `Completed` |
| ~5.6 s | `end` ActionID 3 |

### Validation

| Check | Result |
|-------|--------|
| Game starts | **Yes** (Hades.exe + Proton 11 ARM64) |
| Steam running state | **Yes** (`eDisplayStatus: 4`) |
| Single process add | **Yes** — one `Game process added` (ProcID 2395328) |
| No launch loop | **Yes** — one cancel, one bypassed relaunch |
| No double Steam game | **Yes** — one reaper `AppId=1145360` tree |
| Proton selection preserved | **Yes** — same Proton 11.0 (ARM64) + SLR4 cmdline |
| Steam Input / Stop Game | Not yet explicitly validated (ask user) |

**Answers Q2–Q4:** Cancel stops the first action before process create; `RunGame`
relaunches cleanly; Steam remains the launcher. One-shot bypass works.

Caveat: cancelled action briefly reached `ShowLaunchOption` in the task stream;
relaunch still showed launch-option handling (auto-continued with `"1"`). Fine for
stock Phase 2; route chooser (Phase 11) must cancel before user-visible UI or
accept/suppress that dialog.

---

## Phase 5 — milestone: Hades window in nested KWin (2026-10-05)

**Proven:** Steam launched and tracked Hades (Proton 11 ARM64); the real window
appeared on Frametop’s main nested display (`DISPLAY=:2` / KWin).

### Evidence

- User report: launched on main Wayland display.
- `/tmp/frametop-game-run.log`:
  `overrides=DISPLAY=:2 WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=…/frametop …`
  `argv0=…/steam-launch-wrapper`
- Live `Hades.exe` environ: **`DISPLAY=:2`** (stock was `:1`).
- Steam console CreatingProcess:
  `ft-game-run /…/steam-launch-wrapper … reaper … Proton … Hades.exe`
- `Game process added` / updated with AppID 1145360 — Steam still owns tracking.
- Temporary launch options restored to `""` after verify; marker removed.

### Answers updated

5. Steam-launched game pointed at nested KWin — **Yes** (Proton / X11 via `DISPLAY`).
6. Required overrides — at least `DISPLAY` (+ `XAUTHORITY` / nested runtime from
   plasmashell.env); `WAYLAND_DISPLAY` set but Proton used Xwayland `:2`.
7. Works with Proton — **Yes** (Hades).
10. Steam running state — **Yes** (process added/updated under AppID).
12. User launch options preserved — **Yes** for this probe (empty → wrap → restore).
13. Temporary `SetAppLaunchOptions` — **Viable for controlled probe**; restore ran;
    still need crash-safe automation before shipping.
14. Cleaner per-launch API — not found yet; Option B worked for the experiment.

Treat this as the Stage 3 make-or-break milestone. Next work (chooser UI, VR
classification, SteamVR flat-panel behavior, main-display policy polish) can wait
until you want more complexity.

### Chooser follow-up (2026-10-05)

`steam-ui-patches/game-route` (CDP-armed) cancels `LaunchApp`, shows SteamVR vs
Tovakai, then relaunches. Proven path (**patch v5**):

1. `SetAppLaunchOptions` → `ft-game-run %command%` (verify via app details).
2. Relaunch with `SteamClient.URL.ExecuteSteamURL('steam://run/<appId>')`
   (call on the URL object — extracting the function loses `this`).
   `Apps.RunGame` does **not** apply wraps.
3. **Do not restore options for ~18s** — Steam reads them at `CreatingProcess`,
   often several seconds after `LaunchApp`. Restoring at 2.5s launched stock
   (`DISPLAY=:1`, no wrap log).

Arm: `test/_arm_game_route_chooser.sh`. Auto retest:
`test/_retest_tovakai_wrap_v2.sh`. Invisible popup →
`test/_wait_pick_game_route.sh tovakai`.

---

## Phase checklist (status)

| Phase | Status |
|-------|--------|
| 0 Inspect FrameTop + steam-frame-nix | **Done** |
| 1 Observe GameActionStart on a real launch | **Done** (Hades) |
| 2 Cancel → stock `RunGame` + one-shot bypass | **Done** |
| 3 `ft-game-run` env wrapper | **Done** |
| 4 Temporary `SetAppLaunchOptions` wrap | **Done** (restored) |
| 5 Route one game into nested KWin | **Done — milestone** |
| 6 Native Wayland path | Optional follow-up |
| 7 Steam Input deep check | Informal OK earlier; re-check on routed launch |
| 8–13 SteamVR panel / chooser / prefs | Not started |

---

## Early answers (partial)

1. `RegisterForGameActionStart` — **Yes**, catches SteamVR `LaunchApp` (Hades, source 100).
2. `CancelGameAction` — **Yes**, stops before `CreatingProcess`.
3. `RunGame` relaunch — **Yes**.
4. Steam remains launcher — **Yes**.
5. Point game at nested KWin — **Yes** (Hades → `DISPLAY=:2`).
6. Variables — `DISPLAY` (+ nested `XAUTHORITY` / `XDG_RUNTIME_DIR` / `WAYLAND_DISPLAY` from plasmashell.env); leave DBUS alone.
7. Proton — **Yes**.
8. Native apps — untested.
9. Steam Input — felt normal on stock relaunch; routed launch not separately logged.
10. Running state / Stop Game — Steam tracked wrapped cmdline; Stop Game OK on Phase 2.
11. SteamVR flat-game panel — observe on next routed session (not fully logged here).
12–13. Option B viable for probe with restore marker.
14. No cleaner per-launch API found yet.
15. `bIsVRLaunchOption` + avoid VR-only; launch-option UI still appears.
16. Modal after cancel — not built.
17. Intercept/options in steam-frame-nix; `ft-game-run` + KWin in FrameTop.
18. **Safest next:** document milestone; optional observe SteamVR flat panel on routed
    game; only then prototype chooser in uiPatches.

---

## Safety

- Observe probe: `window.__ftGameRouteProbe.dispose()` or SharedJS reload.
- Disable routing later: remove patch from `uiPatches.patches` / stop `steam-ui-patches`
  (or disable only the routing patch) → stock launches.
- Never leave mutated launch options; never touch Proton prefixes or game files.
