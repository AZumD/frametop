#!/usr/bin/env bash
# Unstick a fully transparent Frametop screen (idle/active opacity 0).
# From WSL/PC:  bash scripts/recover-opacity.sh [SCREEN]
# SCREEN defaults to 1 (main). Sets active=idle=1 and turns gaze attention off.
set -euo pipefail
# shellcheck source=scripts/_env.sh
. "$(dirname "$0")/_env.sh"
N=${1:-1}
on_frame "layout/ft-layout opacity $N 1.0 1.0"
echo "screen $N restored to full opacity (attention off). If still invisible, rebuild/restart ft-screens after syncing."
