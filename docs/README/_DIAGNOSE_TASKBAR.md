# _diagnose_taskbar.sh

Read-only check on the Frame for the spatial toolbar: `ft-taskbar`, toolbar
commands on `@ft_screens`, and layout `toolbar` settings.

## Usage

```
bash test/_diagnose_taskbar.sh
```

## What to look for

- **`ft-taskbar`** should appear in `pgrep` (argv0 `ft-taskbar`).
- **`toolbar state`** on the control socket should answer `ok enabled=… visible=…`,
  not `error unknown command` (that means the live `ft-screens` process predates a
  toolbar build, or the checkout on the Frame lacks `desktop_toolbar.inc`).
- **`has_ft_taskbar=yes`** and taskbar lines in `session/frametop-session.sh` — a
  desktop restart is required for the session script to start `ft-taskbar` automatically.

Spatial toolbar sources live on the `stage2-desktop-toolbar` tree (`frametop-stage1-chrome`).
