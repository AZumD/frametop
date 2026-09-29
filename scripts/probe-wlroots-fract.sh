#!/usr/bin/env bash
set -uo pipefail
~/.local/bin/distrobox enter dev -- bash -lc '
inc=/usr/include/wlroots-0.20
ls "$inc/wlr/types" | grep -iE "fract|view|scale" || true
ls "$inc/wlr/types"/wlr_fractional* 2>/dev/null || echo "no fractional header"
head -80 "$inc/wlr/types/wlr_fractional_scale_v1.h" 2>/dev/null || true
'
