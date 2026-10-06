#!/usr/bin/env bash
# Dependency-light guards for 0.1.0 packaging (VERSION / CHANGELOG / release doc).
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
fail=0
ok() { echo "ok: $*"; }
bad() { echo "FAIL: $*" >&2; fail=1; }

ver=$(tr -d '[:space:]' < "$root/VERSION")
[ "$ver" = "0.1.0" ] && ok "VERSION is 0.1.0" || bad "VERSION is '$ver' (want 0.1.0)"

grep -qE '^## \[0\.1\.0\]' "$root/CHANGELOG.md" && ok "CHANGELOG has 0.1.0 section" || bad "CHANGELOG missing 0.1.0"
grep -q 'desktops.sh revive' "$root/CHANGELOG.md" && ok "CHANGELOG mentions revive" || bad "CHANGELOG revive"
grep -q 'desktop toolbar' "$root/CHANGELOG.md" && ok "CHANGELOG mentions toolbar" || bad "CHANGELOG toolbar"

grep -q '0\.1\.0' "$root/README.md" && ok "README mentions 0.1.0" || bad "README 0.1.0"
grep -q 'desktops.sh revive' "$root/README.md" && ok "README mentions revive" || bad "README revive"
grep -q 'spatial desktop toolbar\|Desktop toolbar\|Start / Tasks' "$root/README.md" && ok "README mentions toolbar" || bad "README toolbar"

grep -q 'VERSION' "$root/scripts/report.sh" && ok "report.sh reads VERSION" || bad "report.sh VERSION"
grep -q '0\.1\.0' "$root/docs/README/RELEASE_0_1_0.md" && ok "RELEASE_0_1_0 present" || bad "RELEASE doc"
grep -q 'revive-desktop\|RELEASE_0_1_0\|VERSION' "$root/docs/README/OVERVIEW.md" && ok "OVERVIEW lists packaging" || bad "OVERVIEW packaging"

[ -f "$root/docs/README/VERSION.md" ] && ok "VERSION.md" || bad "VERSION.md"
[ -f "$root/docs/README/CHANGELOG.md" ] && ok "docs CHANGELOG.md" || bad "docs CHANGELOG.md"

if [ "$fail" -ne 0 ]; then
  echo "release packaging checks failed" >&2
  exit 1
fi
echo "all release packaging checks passed"
