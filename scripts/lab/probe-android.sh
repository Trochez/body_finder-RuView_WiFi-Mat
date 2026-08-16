#!/usr/bin/env bash
set -euo pipefail
OUT=${1:-android-capability-report}
mkdir -p "$OUT"
adb devices -l | tee "$OUT/adb-devices.txt"
mapfile -t DEVS < <(adb devices | awk 'NR>1 && $2=="device" {print $1}')
for d in "${DEVS[@]}"; do
  safe=$(echo "$d" | tr ':/' '__')
  dir="$OUT/$safe"; mkdir -p "$dir"
  adb -s "$d" shell getprop > "$dir/getprop.txt"
  adb -s "$d" shell pm list features > "$dir/features.txt"
  adb -s "$d" shell dumpsys wifi > "$dir/dumpsys-wifi.txt" || true
  adb -s "$d" shell dumpsys bluetooth_manager > "$dir/dumpsys-bluetooth.txt" || true
  adb -s "$d" shell dumpsys sensorservice > "$dir/dumpsys-sensors.txt" || true
  adb -s "$d" shell dumpsys package com.trochez.bodyfinderruview > "$dir/body-finder-package.txt" || true
  printf '%s\n' "$d" > "$dir/device-id.txt"
done

tar -czf "${OUT}.tar.gz" "$OUT"
echo "Created ${OUT}.tar.gz"
