#!/usr/bin/env bash
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
bus="unix:path=$XDG_RUNTIME_DIR/bus"

echo "=== container probe ==="
distrobox enter dev -- python3 "$HOME/dev/frametop/test/probe_launcher_issues.py" 2>&1 | head -60

echo "=== host-exec instrument list ==="
distrobox enter dev -- env DBUS_SESSION_BUS_ADDRESS="$bus" \
  distrobox-host-exec "$HOME/dev/frametop/layout/ft-layout" instrument list 2>&1 | tail -20

echo "=== host-exec remove launcher-2 ==="
distrobox enter dev -- env DBUS_SESSION_BUS_ADDRESS="$bus" \
  distrobox-host-exec "$HOME/dev/frametop/layout/ft-layout" instrument remove launcher-2 2>&1 || echo "remove_exit=$?"

echo "=== after remove ==="
"$HOME/dev/frametop/layout/ft-layout" instrument list 2>&1 | grep launcher || echo '(no launchers)'

echo "=== /run/host apps? ==="
ls /run/host/usr/share/applications 2>/dev/null | head -5 || echo 'no /run/host on host shell'
distrobox enter dev -- bash -lc 'ls /run/host/usr/share/applications 2>/dev/null | wc -l; python3 -c "import sys; sys.path.insert(0,\"$HOME/dev/frametop/layout\"); import ft_desktop; print(ft_desktop.applications_dirs()[:6]); print(len(ft_desktop.list_applications()))"'
