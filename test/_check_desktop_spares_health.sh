#!/usr/bin/env bash
# Thin wrapper around scripts/revive-desktop.sh --check (spares + desktop health).
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck disable=SC1091
. "$root/scripts/_env.sh"
exec bash "$root/scripts/revive-desktop.sh" --check
