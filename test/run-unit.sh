#!/usr/bin/env bash
# Dependency-light regression suite (no Steam Frame / SteamVR / Plasma / PySide).
# Same list as .github/workflows/unit.yml — keep them in sync.
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"

py=python3
command -v "$py" >/dev/null || py=python

fail=0
run() {
  echo "== $* =="
  if "$@"; then
    echo "ok"
  else
    echo "FAIL: $*" >&2
    fail=1
  fi
}

run "$py" test/test_pointer_coords.py
run "$py" test/test_eye_bindings.py
run "$py" test/test_gaze_pointer_removed.py
run "$py" test/test_gaze_attention_order.py
run "$py" test/test_soft_follow_gaze_freeze.py
run "$py" test/test_follow_deadzone.py
run "$py" test/test_mpris.py
run "$py" test/test_spatial_profiles.py
run "$py" test/test_spatial_instruments.py
run "$py" test/test_instrument_visibility.py
run "$py" test/test_instrument_configure_page.py
run "$py" test/test_chrome_layout.py
run "$py" test/test_pointer_ignore.py
run "$py" test/test_screen_conceal.py
run "$py" test/test_overlay_budget_and_games.py
run "$py" test/test_float_phase3.py
run "$py" test/test_float_screens_wiring.py
run "$py" test/test_float_cross_panel_dnd.py
run "$py" test/test_apply_without_head.py
run "$py" test/test_launcher_instrument.py
run "$py" test/test_remove_launcher.py
run "$py" test/test_frame_background.py
run "$py" test/test_frame_background_hdr.py
run "$py" test/test_hands_phase3c.py
run bash test/test_steamvr_client_init.sh
run bash test/test_display_settings_ui.sh
run bash test/test_boot_safety.sh

if [ "$fail" -ne 0 ]; then
  echo "unit suite failed" >&2
  exit 1
fi
echo "all unit suite checks passed"
