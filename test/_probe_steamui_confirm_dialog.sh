#!/usr/bin/env bash
# Find ConfirmDialog / modal helpers in Steam UI bundles on the Frame.
set -u
ROOT=/mnt/c/Users/Antho/Projects/frametop-customized-main
# shellcheck disable=SC1091
source "$ROOT/scripts/_env.sh"
ssh -o BatchMode=yes "$FRAME_HOST" bash -s <<'EOF'
set +e
dir=~/.local/share/Steam/steamui
echo "=== steamui dir ==="
ls "$dir" 2>/dev/null | head -20
echo
echo "=== ConfirmDialog / ShowModal hits ==="
rg -l --no-heading 'ShowConfirmDialog|ConfirmModal|GenericConfirmDialog|showModal' "$dir" 2>/dev/null | head -20
rg -n --no-heading -m 3 'ShowConfirmDialog|GenericConfirmDialog' "$dir"/*.js "$dir"/chunk*.js 2>/dev/null | head -40
echo
echo "=== SetCursorActionset / desktop actionset ==="
rg -n --no-heading -m 5 'SetCursorActionset|cursor.?action.?set|DesktopActionSet' "$dir" 2>/dev/null | head -30
EOF
