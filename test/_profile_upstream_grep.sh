#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/Antho/Projects/frametop-customized-main
git show upstream/main:layout/ft_layout.py > /tmp/up_ft_layout.py
rg -n "profile has|fixed screen|merge_profile|profile_apply|def use\b|windows|apps" /tmp/up_ft_layout.py | head -60
echo ====
rg -n "screen_count|SCREENS=" /tmp/up_ft_layout.py | head -30
