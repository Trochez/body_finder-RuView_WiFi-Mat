#!/usr/bin/env bash
set -u
OUT=${1:-linux-capability-report}
mkdir -p "$OUT"
{
  echo '=== uname ==='; uname -a
  echo '=== os-release ==='; cat /etc/os-release 2>/dev/null
  echo '=== env WSL ==='; env | grep -E '^WSL' || true
  echo '=== ip link ==='; ip link 2>&1 || true
  echo '=== nmcli ==='; nmcli device 2>&1 || true
  echo '=== iw dev ==='; iw dev 2>&1 || true
  echo '=== iw link ==='; for i in $(iw dev 2>/dev/null | awk '$1=="Interface"{print $2}'); do iw dev "$i" link; done
  echo '=== lspci network ==='; lspci -nnk 2>&1 | grep -A4 -Ei 'network|wireless' || true
  echo '=== lsusb ==='; lsusb 2>&1 || true
  echo '=== rfkill ==='; rfkill list 2>&1 || true
  echo '=== bluetooth ==='; bluetoothctl show 2>&1 || true
  echo '=== proc wireless ==='; cat /proc/net/wireless 2>&1 || true
} > "$OUT/system.txt"
tar -czf "${OUT}.tar.gz" "$OUT"
echo "Created ${OUT}.tar.gz"
