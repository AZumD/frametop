#!/usr/bin/env bash
# Thin wrapper: prefer scripts/revive-desktop.sh (0.1.0 revive path).
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck disable=SC1091
. "$root/scripts/_env.sh"
exec bash "$root/scripts/revive-desktop.sh" --force
