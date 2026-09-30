#!/usr/bin/env bash
# Rebuild ft-screens on the Frame (inside distrobox). Does not restart the session.
# Thin wrapper around screens/build.sh so callers need not know FRAME_REPO layout.
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
exec "$root/screens/build.sh"
