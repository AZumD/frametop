#!/usr/bin/env bash
# Smoke-check boot-safety units and scripts (syntax + expected hardening strings).
# Run on a PC with bash, or on the Frame:
#   bash test/test_boot_safety.sh
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
fail=0
ok() { echo "ok: $*"; }
bad() { echo "FAIL: $*" >&2; fail=1; }
has() { grep -q -- "$1" "$2" && ok "has $1 in $(basename "$2")" || bad "missing $1 in $2"; }
lacks() { if grep -q -- "$1" "$2"; then bad "unexpected $1 in $2"; else ok "lacks $1 in $(basename "$2")"; fi; }

for f in install.sh desktops.sh scripts/recover-vr.sh pointer/driver/install.sh pointer/helper/run.sh; do
  bash -n "$root/$f"
  ok "bash -n $f"
done

relay="$root/input/frametop-input-relay.service"
pointer="$root/pointer/helper/frametop-pointer.service"

has 'TimeoutStartSec=20' "$relay"
has 'WantedBy=steamvr.service' "$relay"
if grep -E '^WantedBy=.*default\.target' "$relay" >/dev/null; then
  bad "WantedBy still lists default.target in relay unit"
else
  ok "WantedBy excludes default.target"
fi
has 'TimeoutStartSec=45' "$pointer"
has 'After=steamvr.service' "$pointer"
lacks 'Before=steamvr' "$pointer"

has '--with-pointer' "$root/install.sh"
has 'recover-vr.sh' "$root/install.sh"
has 'OPTIONAL' "$root/pointer/driver/install.sh"
has 'vrpathreg' "$root/scripts/recover-vr.sh"
has 'frametop-pointer.service' "$root/scripts/recover-vr.sh"
has 'frametop-input-relay.service' "$root/scripts/recover-vr.sh"

has 'AnchorDevice' "$root/screens/vr.cpp"
has 'k_unTrackedDeviceIndex_Hmd' "$root/screens/vr.cpp"
has 'IsHandController(s.pinned)' "$root/screens/vr.cpp"

has 'profile list' "$root/layout/ft_layout.py"
has '--duration' "$root/layout/ft_layout.py"
has 'frametop-layout-profiles.json' "$root/layout/ft_layout.py"

if [ "$fail" -ne 0 ]; then
  echo "boot-safety checks failed" >&2
  exit 1
fi
echo "all boot-safety checks passed"
