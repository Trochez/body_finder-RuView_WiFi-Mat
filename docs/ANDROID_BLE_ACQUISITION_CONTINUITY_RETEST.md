# Android BLE Acquisition Continuity Retest — experimental.8

## Purpose

Validate the last known physical bottleneck after `experimental.7`: **per-direction BLE advertisement callback continuity** on Pixel 10 Pro, Pixel 7 Pro and Lenovo TB-J606L.

This test does **not** recalibrate BLE distance and does not validate human detection. Human scanning must remain disabled.

## Build truth to verify

Before testing, Expert mode must show:

```text
Build: 0.2.0-experimental.8
protocol: 2
profile: android-ble-lab-v1
validated: true
physical confidence: COARSE
valid domain: 0.5–5.0 m
```

BLE diagnostics must show the primary strategy:

```text
scan_strategy = LOW_LATENCY_SOFTWARE_FILTERED_ALL_MATCHES
hardware_filter_count = 0
match_mode = AGGRESSIVE          # API >=23
num_matches = MAX_ADVERTISEMENT  # API >=23
report_delay_ms = 0
software_body_finder_filter = true
advertise_tx_power = MEDIUM_FROZEN_FOR_CALIBRATION
```

The continuity policy must remain:

```text
fresh_ms = 5000
holdover_max_ms = 10000
hard_expiry_ms = 10000
sigma_aging_m_per_s = 0.15
```

## Devices

Use the same APK on:

1. Pixel 10 Pro / API 37
2. Pixel 7 Pro / API 34
3. Lenovo TB-J606L / API 30

## Preparation

On all devices:

- Wi-Fi ON and same local network;
- Bluetooth ON;
- Battery Saver OFF;
- screen ON for the entire test;
- Body Finder in foreground;
- do not hold or move devices during the run.

On Lenovo/API30 also keep Location ON.

Use the same non-collinear triangular layout used for the prior metric-geometry tests. Confirm only that all three pair distances remain within **0.5–5.0 m**. No new ground-truth file is required if the devices have not moved materially.

## Procedure

1. Install `body-finder-ruview-universal.apk` from the new release on all three devices.
2. Open Body Finder on all three.
3. Wait **30 seconds** before starting the validation run.
4. Verify each device sees:
   - `3 nodes`;
   - `2 BLE PEERS`;
   - no permission/service error.
5. Open **Expert** and verify the experimental.8 acquisition strategy above.
6. Start **Iniciar corrida de validación / Start validation run** on all three devices within a few seconds of each other.
7. Leave the three devices stationary for **exactly 5 minutes**.
8. Do not calibrate the empty scene and do not attempt human scanning.
9. At 5 minutes, press **Finalizar corrida de validación / End validation run** on each device.
10. Wait approximately 2 seconds.
11. Capture screenshots.
12. Use **Compartir JSON completo de prueba / Share complete test JSON** on each device.

## Evidence filenames

Save the complete JSON/text exports as:

```text
pixel10_acquisition.txt
pixel7_acquisition.txt
lenovo_acquisition.txt
```

Screenshots requested:

```text
pixel10_radar.png
pixel10_validation.png
pixel10_ble.png
pixel10_system_ranging.png

pixel7_radar.png
pixel7_validation.png
pixel7_ble.png

lenovo_radar.png
lenovo_validation.png
lenovo_ble.png
```

If a single Expert screenshot does not contain the full BLE block, use additional numbered screenshots.

## Fields that must be present

For every observer→peer direction, the `acquisition` block should expose:

```text
acquisition_health
current_gap_ms
callback_count
valid_rssi_callback_count
invalid_rssi_callback_count
callback_rate_hz
valid_callback_rate_hz
mean_interarrival_ms
max_interarrival_ms
p50_interarrival_ms
p95_interarrival_ms
gap_gt_1s_count
gap_gt_2s_count
gap_gt_5s_count
gap_gt_10s_count
run_callback_delta
run_valid_callback_delta
run_invalid_callback_delta
run_gap_gt_1s_delta
run_gap_gt_2s_delta
run_gap_gt_5s_delta
run_gap_gt_10s_delta
```

The validation run must expose:

```text
all_peer_uptime_percent
fresh_metric_range_uptime_percent
usable_metric_range_uptime_percent
holdover_metric_uptime_percent
geometry_2d_uptime_percent
peer_expire_delta
scan_restart_delta
```

On Pixel 10/API37, also capture:

```text
system_ranging.state
system_ranging.result_count
system_ranging.close_failure_count
system_ranging.closes_since_real_result
system_ranging.ble_yield_active
system_ranging.ble_yield_count
system_ranging.ble_yield_reason
```

## Expected behavior

A healthy direction should usually have:

```text
acquisition_health = ACQUISITION_HEALTHY
valid_callback_rate_hz >= 0.6 preferred
p95_interarrival_ms <= 5000 preferred
```

A sparse direction is not automatically a failure if holdover still keeps the metric range usable. However, unexplained repeated gaps >10 seconds must be investigated.

Pixel 10 may enter:

```text
system_ranging.state = BLE_ACQUISITION_YIELD
```

This is expected when RangingManager repeatedly closes without a real platform distance. It must not disable the independent Body Finder BLE scanner.

## Hard acceptance gates

The increment passes physical acceptance only if **all three devices** meet:

```text
usable_metric_range_uptime_percent >= 90%
geometry_2d_uptime_percent >= 90%
peer_expire_delta = 0
```

Preferred:

```text
all_peer_uptime_percent >= 99%
scan_restart_delta = 0
```

## Truth/safety gates

The following must also remain true:

```text
profile = android-ble-lab-v1
RSSI@1m = -69.19
n = 3.62
metric domain = 0.5–5.0 m
min samples = 3
fresh = 5 s
holdover = 10 s
human_scanning_enabled = false
manual_geometry_override = false
```

No result is considered a pass if the uptime target was achieved by relaxing those invariants.

## Package to return

Create:

```text
experimental8-acquisition/
├── pixel10_acquisition.txt
├── pixel7_acquisition.txt
├── lenovo_acquisition.txt
└── screenshots/
    ├── pixel10_radar.png
    ├── pixel10_validation.png
    ├── pixel10_ble.png
    ├── pixel10_system_ranging.png
    ├── pixel7_radar.png
    ├── pixel7_validation.png
    ├── pixel7_ble.png
    ├── lenovo_radar.png
    ├── lenovo_validation.png
    └── lenovo_ble.png
```

Compress it and return the ZIP for analysis.

## What will be calculated from the evidence

For every observer→peer direction:

- total and valid callback density;
- p50/p95 inter-arrival;
- maximum inter-arrival;
- number of >1/2/5/10 s gaps;
- fresh vs holdover contribution;
- Pixel10 system-ranging yield behavior.

For every device:

- peer uptime;
- fresh metric uptime;
- usable metric uptime;
- holdover share;
- Geometry 2D uptime;
- scanner restarts and peer expiry.

Only after this gate passes should a new increment consider enabling human-scene tests.
