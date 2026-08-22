# Android dev-11 final acceptance retest

## Install
Install **the same** `body-finder-ruview-universal.apk` from release `dev-11` on Pixel 10 Pro, Pixel 7 Pro and Lenovo TB-J606L. Confirm the UI says `0.2.0-experimental.11`.

## Prepare
On all three: Bluetooth ON, Battery Saver OFF, screen ON, Body Finder foreground, same session. On Lenovo also Location ON. Arrange a non-collinear triangle with every pair between 0.5 m and 5.0 m. Measure the three distances with a tape and save them separately; do not enter them in the app.

## Warm-up (30 s)
On each device verify: `nodes=3`, `BLE peers=2`, strategy `FILTERED_PRIMARY`, filter `MANUFACTURER_FILTERED`, hardware filter count > 0 and `environment_valid=true`.

## Long run
1. Tap **Start validation run** on all three.
2. Do not move devices for **at least 5 minutes**.
3. Tap **End validation run** on all three.
4. Verify `snapshot_frozen=true`, schema `2`, elapsed >= 300000 ms.
5. Export JSON from each device as `*_run_long_export1.json`.
6. Keep apps active for >=3 more minutes.
7. Export the same selected run again as `*_run_long_export2.json`.

## History preservation
1. Start a second short run, wait a few seconds, End.
2. In **Validation run**, tap the previous long `run_id`.
3. Export it as `*_run_long_after_short_run.json`.
4. The long snapshot must be identical across all three exports.

## Validate on Ubuntu/WSL/Windows
Extract `body-finder-validation-tools.zip`, then for each device run:
```bash
python3 compare_validation_snapshots.py export1.json export2.json --run-id <LONG_RUN_ID>
python3 compare_validation_snapshots.py export1.json after_short.json --run-id <LONG_RUN_ID>
python3 validate_recovery_timeline.py export1.json
python3 validate_peer_semantics.py export1.json
python3 validate_geometry_snapshot.py export1.json
```
All commands must print `PASS`.

## Hard gates per device
- `snapshot_frozen=true`
- `elapsed_ms >= 300000`
- `usable_metric_range_uptime_percent >= 90`
- `geometry_2d_uptime_percent >= 90`
- `peer_expire_delta = 0`
- `recovery_attempt_delta <= 3`
- `environment_valid=true`
- timeline seq/wall/elapsed monotonic
- `BF_COHORT_STALLED => cohort_health=BF_COHORT_STALLED`
- max one first-valid callback per recovery generation
- previous long run survives short run
- geometry-at-End remains immutable

Accuracy remains informative and `COARSE`; it is not a recalibration gate in dev-11. Human scanning and rescue-use validation remain disabled.
