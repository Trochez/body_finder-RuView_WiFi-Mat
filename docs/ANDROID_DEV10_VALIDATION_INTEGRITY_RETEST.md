# Body Finder – RuView dev-10 — detailed 3-Android validation-integrity retest

## Goal
Verify that dev-9 BLE continuity remains >=90% while a completed `validation_run` is immutable after End. Human localization/rescue testing is NOT authorized.

## Devices and setup
Use the same **Pixel 10 Pro, Pixel 7 Pro and Lenovo TB-J606L**. Install the same `body-finder-ruview-universal.apk` from release `dev-10` on all three. Battery Saver OFF, Bluetooth ON, screens ON, app foreground, same LAN/session; Lenovo Location ON. Place a non-collinear triangle with every physical pair distance between 0.5 and 5.0 m and do not move it.

## Warm-up
Open all three apps, wait 30 s, verify on every device: 3 nodes, 2 BLE peers, logical strategy FILTERED_PRIMARY, filter mode MANUFACTURER_FILTERED, hardware filter count >0, field service RUNNING and environment valid.

## Five-minute run
Start Validation Run on all three. Confirm `active=true` and leave them stationary exactly 5 minutes. Do not lock screens, change apps/radios or restart scanning.

## End and Export #1
End each run, wait ~2 s, confirm `active=false` and `snapshot_frozen=true`. Capture Radar + Validation + Expert/acquisition; on Pixel10 also System Ranging. Export:
`pixel10_dev10_export1.json`, `pixel7_dev10_export1.json`, `lenovo_dev10_export1.json`.

## Mandatory post-End period
Do NOT start another run or close the apps. Leave all three running for 3 more minutes. Live runtime counters outside `validation_run` may change.

## Export #2
Capture Validation again and export `pixel10_dev10_export2.json`, `pixel7_dev10_export2.json`, `lenovo_dev10_export2.json`.

## Compare immutable snapshots
Extract `body-finder-validation-tools.zip` and run:
```bash
python3 compare_validation_snapshots.py pixel10_dev10_export1.json pixel10_dev10_export2.json
python3 compare_validation_snapshots.py pixel7_dev10_export1.json pixel7_dev10_export2.json
python3 compare_validation_snapshots.py lenovo_dev10_export1.json lenovo_dev10_export2.json
```
Each must print `PASS: completed validation snapshot is immutable`.

## Hard gates (3/3)
- snapshot_frozen=true and Export1 validation_run == Export2 validation_run
- usable_metric_range_uptime_percent >=90
- geometry_2d_uptime_percent >=90
- peer_expire_delta=0
- recovery_attempt_delta<=3
- environment_valid=true
- timeline present; recoveries reconstruct stall → request → unfiltered recovery → callback → success → filtered probe/primary.

## Return evidence
Six JSON exports, three comparator TXT outputs, screenshots named by device (`*_radar`, `*_validation_end`, `*_validation_plus3m`, `*_acquisition`, plus `pixel10_*_ranging`) and a TXT with measured physical pair distances. Zip as `dev10-3android-validation-integrity-evidence.zip`.
