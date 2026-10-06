#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/Antho/Projects/frametop-customized-main
git switch -c integrate-upstream-phase3-floating-2026-10-02 2>/dev/null || git switch integrate-upstream-phase3-floating-2026-10-02
echo "branch=$(git branch --show-current) HEAD=$(git rev-parse --short HEAD)"
for c in 87a402c6 c2e5e861 6122b7eb c8fc6351 1e83f96b f3218782 00dfd613 38843a47 c3785bb4 858dbe15 0af087c7 369736f0; do
  echo "==== $c ===="
  git log -1 --oneline "$c" 2>/dev/null || echo MISSING
  git show --stat --format='' "$c" 2>/dev/null | head -40 || true
done
echo "==== upstream/main tree float/decoration ===="
git ls-tree --name-only upstream/main float decoration 2>/dev/null || true
git ls-tree --name-only -r upstream/main float decoration | head -80
echo "==== floating-windows.md outline ===="
git show upstream/main:docs/floating-windows.md 2>/dev/null | head -150
