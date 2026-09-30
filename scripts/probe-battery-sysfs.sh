#!/usr/bin/env bash
# Probe Steam Frame power_supply nodes for headset battery.
set -euo pipefail
echo "=== /sys/class/power_supply ==="
ls -la /sys/class/power_supply || true
for d in /sys/class/power_supply/*; do
  [ -d "$d" ] || continue
  echo "=== $d ==="
  for f in type scope capacity status present technology manufacturer model_name serial_number \
           charge_full charge_full_design charge_now energy_full energy_now voltage_now \
           uevent; do
    if [ -r "$d/$f" ]; then
      printf '%s: ' "$f"
      tr '\n' ' ' <"$d/$f"
      echo
    fi
  done
done
echo "=== upower (if any) ==="
command -v upower >/dev/null && upower -e || echo "no upower"
echo "=== OpenVR prop note ==="
echo "Prop_DeviceBatteryPercentage_Float may also exist for HMD via SteamVR"
