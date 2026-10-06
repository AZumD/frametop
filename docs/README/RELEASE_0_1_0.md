# RELEASE_0_1_0

Frametop fork **0.1.0** release notes and smoke checklist.

## Promise

Cold start → desktop with **toolbar chrome (default on)** → use apps → enter flat/VR game without stealing controllers → return with **`desktops.sh revive`** if needed — without a `_fix_desktop_*` ritual.

## In

- Spatial toolbar / `ft-taskbar` / dock
- AppActivity ownership
- `scripts/revive-desktop.sh` / `desktops.sh revive`
- Packaging: `VERSION`, root `CHANGELOG.md`, this doc

## Out (see CHANGELOG)

Game-route permanent chooser; float Meta+D / FLOAT_SLOTS UI; hands gestures; float tear-off theater.

## Smoke (wear the headset)

1. Cold: Launch Desktop → screens + toolbar; Start opens an app
2. Task tile / focus / minimize
3. Dock a screen to the dashbar; undock restores follow
4. Open SteamVR dashboard → toolbar yields; return without blank tiles
5. Enter a VR scene game → screens hide; controllers stay in-game
6. Flatscreen / gamepad mode → no laser steal mid-game
7. Exit game → if desktop is broken, `desktops.sh revive` restores it
8. Displays → switch a profile; toolbar survives
9. `scripts/recover-vr.sh` still documented as SteamVR-only escape hatch

## Tag

```
git tag -a v0.1.0 -m "Frametop 0.1.0"
```

`VERSION` must read `0.1.0` and match the CHANGELOG section.

## Related

[VERSION.md](VERSION.md), [CHANGELOG.md](CHANGELOG.md), [REVIVE-DESKTOP.md](REVIVE-DESKTOP.md), [DESKTOP_TOOLBAR.md](DESKTOP_TOOLBAR.md)
