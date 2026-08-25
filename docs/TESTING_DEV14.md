# TESTING DEV14 — final physical acceptance

No screenshots are required. Exported JSON/JSONL is the diagnostic source of truth.

## 1. Verify release
Download every asset from prerelease `dev-14`. On Ubuntu/WSL run `sha256sum -c SHA256SUMS.txt`; on Windows PowerShell compare `Get-FileHash -Algorithm SHA256` with `SHA256SUMS.txt`. Confirm `release-verification.json` says PASS.

## 2. Android preparation
Use the exact same `BodyFinder-dev14-universal.apk` on Pixel 10 Pro, Pixel 7 Pro and Lenovo TB-J606L. Uninstall older builds if Android refuses replacement. Enable Bluetooth; Battery Saver OFF; screen ON; app visible/foreground. Use one common session and wait until each device reports preflight `ready=true` and at least two BLE peers. Do not enter node coordinates or distances in the app.

## 3. Physical layout
Place the three devices as a static non-collinear triangle. Every pair distance must be 0.5–5.0 m. Measure with tape and write only those three distances to `ground-truth.json`.

## 4. Runs on each Android
1. Start validation; keep the app foreground for at least 330 s.
2. End; export the completed long run as `<device>-long-1.json`.
3. Keep app running at least 180 s; re-export the same completed run as `<device>-long-2.json`.
4. Start a 45–60 s diagnostic run; end it.
5. Reselect the original long run and export `<device>-long-post-short.json`.

Names: `pixel10-*`, `pixel7-*`, `lenovo-*`, plus `ground-truth.json`.

## 5. Automated validation (Ubuntu or WSL)
Unzip `body-finder-validation-tools.zip`, then run:
```bash
python3 validate_dev14_hard_gates.py pixel10-long-1.json pixel7-long-1.json lenovo-long-1.json
python3 validate_timeline_causality.py pixel10-long-1.json
python3 validate_peer_starvation_recovery.py pixel10-long-1.json
python3 validate_environment_intervals.py pixel10-long-1.json
python3 compare_validation_snapshots.py pixel10-long-1.json pixel10-long-2.json
python3 compare_validation_snapshots.py pixel10-long-1.json pixel10-long-post-short.json
python3 build_acceptance_report.py . --output acceptance_report.json
python3 calculate_accuracy_report.py ground-truth.json . --output accuracy_report.json
```
Repeat the single-file validators for Pixel 7 and Lenovo. The long-run validator must PASS; the long re-exports must be immutable; the short run must not replace/change the selected long snapshot.

## 6. Windows native smoke
Extract `body-finder-node-windows-x86_64.zip`, run `body-finder-node.exe --help`, then use Python validators from PowerShell exactly as above. Linux tar/deb and Windows node artifacts are smoke-tested independently of the 3-Android acceptance. iOS simulator ZIP is a build artifact only, not part of physical BLE acceptance.

Final GO requires automated G0–G16 PASS on all three long snapshots and aggregate reports. Accuracy is informative only; do not alter calibration automatically.
