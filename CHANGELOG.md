# Changelog

All notable changes to this Frametop fork are recorded here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] — 2026-10-06

First named cut of this fork: a coherent nested-desktop **shell**, not a kit of experiments.

### Added

- Spatial **desktop toolbar** (Start / Tasks / Displays / Tray), on by default; host `ft-taskbar` + `layout/ft_toolbar.py` / dock
- **AppActivity** — one ownership model for VR-scene / flatscreen hide and OutsideGames lasers
- **`desktops.sh revive`** / `scripts/revive-desktop.sh` — one path back to a working desktop after a game or SteamVR bounce (does not restart SteamVR)
- Unit coverage for toolbar, dock, taskbar model, AppActivity, and revive guards in `test/run-unit.sh`

### Changed

- Under-screen profile digits removed; Displays on the toolbar owns profile slots
- Screen chrome includes **dock to dashbar**
- README / OVERVIEW document the 0.1.0 shell promise and revive path

### Deferred (not in 0.1.0)

- Permanent Steam→Tovakai game-route chooser (`steam-ui-patches/game-route`)
- FLOAT_SLOTS / FLOAT_MARGIN Display Settings UI; Meta+D keeps floating windows
- Hands pinch/gestures, float tear-off / dock-by-drag, instrument V1 extras

### Tested on

- One Steam Frame (SteamOS 0.3.0 build 20260922, SteamVR 2.17.10) — update this note when re-verified

[0.1.0]: https://github.com/AZumD/frametop/releases/tag/v0.1.0-fork

Note: git tag `v0.1.0` already exists in history from upstream; this fork cut is tagged `v0.1.0-fork` while `VERSION` / product version remain `0.1.0`.
