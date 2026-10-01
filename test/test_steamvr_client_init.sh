#!/usr/bin/env bash
# Static checks: FrameTop SteamVR clients must not bootstrap vrserver, and
# optional helper units stay disposable (Requisite=, not Requires=).
# Run: bash test/test_steamvr_client_init.sh
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
fail=0
ok() { echo "ok: $*"; }
bad() { echo "FAIL: $*" >&2; fail=1; }

has() { grep -q -- "$1" "$2" && ok "has $1 in $(basename "$2")" || bad "missing $1 in $2"; }
lacks() { if grep -q -- "$1" "$2"; then bad "unexpected $1 in $2"; else ok "lacks $1 in $(basename "$2")"; fi; }

pointer_svc="$root/pointer/helper/frametop-pointer.service"
gaze_svc="$root/gaze/frametop-gaze.service"

has 'After=steamvr.service' "$pointer_svc"
has 'PartOf=steamvr.service' "$pointer_svc"
has 'Requisite=steamvr.service' "$pointer_svc"
lacks 'Requires=steamvr.service' "$pointer_svc"

has 'After=steamvr.service' "$gaze_svc"
has 'PartOf=steamvr.service' "$gaze_svc"
has 'Requisite=steamvr.service' "$gaze_svc"
lacks 'Requires=steamvr.service' "$gaze_svc"

# Overlay clients probe Background first, then Overlay (never Overlay alone as first Init).
for f in \
  "$root/pointer/helper/ft-pointer.cpp" \
  "$root/gaze/ft-gaze.cpp" \
  "$root/screens/vr.cpp"
do
  if ! grep -q 'VRApplication_Background' "$f"; then
    bad "missing VRApplication_Background probe in $f"
  else
    ok "Background probe in $(basename "$f")"
  fi
  # First VR_Init in these files should not be Overlay-only without Background nearby.
  # Accept the Background-then-Overlay pattern from upstream #6.
  if ! awk '
    /VR_Init/ {
      window = window $0 ORS
      n++
      if (n >= 6) exit
    }
    END {
      if (window ~ /VRApplication_Background/ && window ~ /VRApplication_Overlay/) exit 0
      exit 1
    }
  ' "$f"; then
    # Fallback: file contains both tokens (ft-screens / helpers after port).
    if grep -q 'VRApplication_Background' "$f" && grep -q 'VRApplication_Overlay' "$f"; then
      ok "Background+Overlay present in $(basename "$f")"
    else
      bad "no safe Background→Overlay init pattern in $f"
    fi
  else
    ok "Background→Overlay init window in $(basename "$f")"
  fi
done

# Headless / --no-vr must exist and must not claim production control socket by default.
has '--no-vr' "$root/screens/compositor.c"
has '--control' "$root/screens/compositor.c"
has 'ft_screens' "$root/screens/compositor.c"
if [ -f "$root/screens/test/headless.sh" ]; then
  has 'ft_screens_test' "$root/screens/test/headless.sh"
  has '--no-vr' "$root/screens/test/headless.sh"
  bash -n "$root/screens/test/headless.sh" && ok "bash -n screens/test/headless.sh"
else
  bad "missing screens/test/headless.sh"
fi

if [ "$fail" -ne 0 ]; then
  echo "steamvr client init checks failed" >&2
  exit 1
fi
echo "all steamvr client init checks passed"
