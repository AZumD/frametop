#!/usr/bin/env bash
# Offline check: empty steamvr-pending.path must be treated as poison for SteamVR path.
# Mirrors the recover-vr / Frame black-screen failure mode (realpath: '').
#   bash test/test_steamvr_pending_path.sh
set -euo pipefail

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

pending="$tmp/steamvr-pending.path"

# Empty file → should be removed by the same condition recover-vr uses.
: >"$pending"
if [ -e "$pending" ] && [ ! -s "$pending" ]; then
  rm -f "$pending"
else
  echo "FAIL: empty pending was not detected" >&2
  exit 1
fi
[ ! -e "$pending" ] || { echo "FAIL: empty pending still present" >&2; exit 1; }
echo "ok: empty pending removed"

# Non-empty pending → leave alone.
echo /opt/steamvr >"$pending"
if [ -e "$pending" ] && [ ! -s "$pending" ]; then
  echo "FAIL: non-empty pending treated as empty" >&2
  exit 1
fi
[ -s "$pending" ] || { echo "FAIL: non-empty pending missing" >&2; exit 1; }
echo "ok: non-empty pending kept"

# Missing → ok.
rm -f "$pending"
if [ -e "$pending" ]; then
  echo "FAIL: pending should be absent" >&2
  exit 1
fi
echo "ok: missing pending is fine"
echo "all steamvr-pending-path checks passed"
