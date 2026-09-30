#!/usr/bin/env bash
# Detail probe for Frame headset battery candidates.
set -euo pipefail
echo "=== listing ==="
ls -la /sys/class/power_supply
for name in max1720x_bat_7-36 pm8550b-charger; do
  d="/sys/class/power_supply/$name"
  echo "=== $d ==="
  [ -d "$d" ] || { echo missing; continue; }
  ls -la "$d"
  for f in type scope capacity capacity_level status present technology manufacturer \
           model_name serial_number charge_full charge_full_design charge_now \
           energy_full energy_now voltage_now current_now power_now online \
           usb_type; do
    if [ -r "$d/$f" ]; then
      printf '%s=' "$f"
      cat "$d/$f"
    fi
  done
done
# Prefer Battery-typed nodes with capacity
echo "=== candidates (type=Battery + capacity) ==="
for d in /sys/class/power_supply/*; do
  [ -r "$d/type" ] || continue
  t=$(cat "$d/type")
  [ "$t" = "Battery" ] || continue
  cap=""
  [ -r "$d/capacity" ] && cap=$(cat "$d/capacity")
  echo "$d type=$t capacity=${cap:-n/a} status=$(cat "$d/status" 2>/dev/null || echo n/a)"
done
