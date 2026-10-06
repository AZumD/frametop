#!/usr/bin/env bash
# Run Phase 3 headless + regression suite from WSL/Linux.
set -euo pipefail
cd /mnt/c/Users/Antho/Projects/frametop-customized-main

fail=0
run() {
  echo "==== $*"
  if "$@"; then
    echo "OK: $*"
  else
    echo "FAIL: $*"
    fail=1
  fi
}

run python3 -m py_compile input/input-relay.py
run python3 test/test_float_screens_wiring.py
run python3 test/test_float_phase3.py
run python3 test/test_input_relay_control.py
run python3 test/test_vr_keyboard_relay.py
run python3 test/test_pointer_ignore.py
run python3 test/test_screen_conceal.py
run bash test/test_steamvr_client_init.sh
run bash test/test_boot_safety.sh
run git diff --check

# Launcher/instrument WIP tests if present (do not fail the suite on WIP noise)
if [[ -f test/test_launcher_remove_and_apps.py ]]; then
  echo "==== launcher WIP (informational)"
  python3 test/test_launcher_remove_and_apps.py || echo "WARN: launcher WIP test failed (not blocking)"
fi

exit $fail
