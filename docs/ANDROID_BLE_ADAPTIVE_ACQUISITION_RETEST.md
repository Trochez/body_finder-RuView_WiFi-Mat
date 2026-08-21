# Android BLE Adaptive Acquisition Retest — experimental.9

## Goal
Validate that Pixel receivers recover a stalled Body Finder cohort without relaxing metric truth.

## Required build truth
- Build `0.2.0-experimental.9`, protocol 2.
- `android-ble-lab-v1`, validated COARSE, 0.5–5.0 m.
- minSamples=3, fresh=5s, holdover=10s, sigma aging=0.15 m/s.
- primary strategy `FILTERED_PRIMARY`; recovery `UNFILTERED_RECOVERY`.
- human scanning disabled.

## Environment
Use the same universal APK on Pixel 10 Pro, Pixel 7 Pro and Lenovo TB-J606L. Same LAN, Bluetooth ON, Battery Saver OFF, screen ON, app foreground. Lenovo Location ON. Keep a non-collinear triangle with all pair distances within 0.5–5.0 m.

The app must refuse to start a validation run if Battery Saver is ON, screen is OFF, the app is not foreground, Bluetooth is OFF or the field service is not RUNNING.

## Procedure
1. Install the `body-finder-ruview-universal.apk` from the experimental.9 prerelease on all three devices.
2. Open all three apps and wait 30 s.
3. Verify `3 nodes`, `2 BLE PEERS`, `FILTERED_PRIMARY`, `global_scanner_health=GLOBAL_SCANNER_HEALTHY` and no environment error.
4. Start validation runs on all three within a few seconds.
5. Leave devices stationary for exactly 5 minutes; do not background the app or perform human scanning.
6. End validation run on all three, wait ~2 s, capture screenshots, then Share complete test JSON.

## Hard gates
Every device must satisfy:
- `environment_valid=true`
- `usable_metric_range_uptime_percent >= 90`
- `geometry_2d_uptime_percent >= 90`
- `peer_expire_delta = 0`
Preferred: `all_peer_uptime_percent >= 99`, `scan_restart_delta <= 3`.

## Acquisition evidence
Capture/export:
- `global_scanner_health`
- `body_finder_cohort_health`
- `acquisition_strategy`
- `strategy_transition_count`
- `cohort_stall_count`
- `cohort_recovery_count`
- `cohort_recovery_failure_count`
- `cohort_recovery_last_latency_ms`
- `filtered_mode_total_ms`
- `unfiltered_recovery_total_ms`
- `restart_suppressed_by_cooldown_count`
- expected/recent known peer counts
- per-peer callback rate, p95 inter-arrival and >1/2/5/10s gap counters, including filtered/unfiltered callback counts.

## Pixel 10
Also capture the `system_ranging` block, including BLE acquisition yield state/count/reason.

## Files to return
```
experimental9-adaptive-acquisition/
├── pixel10_adaptive_acquisition.txt
├── pixel7_adaptive_acquisition.txt
├── lenovo_adaptive_acquisition.txt
└── screenshots/
    ├── pixel10_radar.png
    ├── pixel10_validation.png
    ├── pixel10_ble.png
    ├── pixel10_strategy.png
    ├── pixel10_system_ranging.png
    ├── pixel7_radar.png
    ├── pixel7_validation.png
    ├── pixel7_ble.png
    ├── pixel7_strategy.png
    ├── lenovo_radar.png
    ├── lenovo_validation.png
    ├── lenovo_ble.png
    └── lenovo_strategy.png
```
Zip this directory and return it for analysis.
