#!/usr/bin/env bash
# Run QML load probe inside the Frame's dev container.
set -euo pipefail
repo=${1:-$HOME/dev/frametop}
export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
export DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}
"$repo/scripts/container-up.sh"
exec "$HOME/.local/bin/distrobox" enter dev -- env QT_QPA_PLATFORM=offscreen \
  python3 "$repo/test/probe_qml_load.py"
