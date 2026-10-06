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
grep -q 'v0\.1\.0-fork' "$root/CHANGELOG.md" && ok "CHANGELOG notes v0.1.0-fork tag" || bad "CHANGELOG fork tag"
if git -C "$root" rev-parse -q --verify refs/tags/v0.1.0-fork >/dev/null; then
  tip=$(git -C "$root" rev-list -n1 v0.1.0-fork)
  head=$(git -C "$root" rev-parse HEAD)
  # Allow the tag to sit on the packaging commit or a later tip that contains it.
  if git -C "$root" merge-base --is-ancestor "$tip" "$head" 2>/dev/null || [ "$tip" = "$head" ]; then
    ok "tag v0.1.0-fork present"
  else
    bad "tag v0.1.0-fork does not point at an ancestor of HEAD"
  fi
else
  bad "tag v0.1.0-fork missing"
fi
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
