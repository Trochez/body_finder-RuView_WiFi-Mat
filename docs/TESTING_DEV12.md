# TESTING_DEV12

This release is acceptance-tested from exported JSON. Screenshots are not required and are not acceptance evidence.

## 1. Verify the release before installing anything
Download every `dev-12` asset into one directory. On Ubuntu/WSL run `sha256sum -c SHA256SUMS.txt`; on Windows PowerShell compare each file with `Get-FileHash <file> -Algorithm SHA256` against `SHA256SUMS.txt`. Open `release-verification.json` and require `published_release_verifier=PASS`, `sha256sums_verified=true`, `manifest_verified=true`, and `mandatory_assets_verified=true`. Open `release-manifest.json` and require `release=dev-12`, `version=0.2.0-experimental.12`, `json_evidence_self_contained=true`, and `screenshots_required_for_acceptance=false`.

## 2. Android primary field test — authoritative acceptance test
Install `BodyFinder-dev12-universal.apk` (same bytes as `body-finder-ruview-universal.apk`) on Pixel 10 Pro, Pixel 7 Pro and Lenovo TB-J606L. Use the same session `body-finder-lab`. Keep all three stationary in a triangle with every pair between 0.5 m and 5.0 m. Ground-truth tape distances are optional accuracy input only; never enter them into the app.

Open Expert on every phone and wait for `Validation preflight.ready=true`. Required truth: Bluetooth ON, Battery Saver OFF, screen ON, app foreground, foreground service RUNNING, BLE scanner running, at least two expected BLE peers, `FILTERED_PRIMARY`, manufacturer-filtered acquisition and `hardware_filter_count>0`; Android <=11 additionally requires Location ON. If Start Validation is rejected, fix the exported preflight issue instead of bypassing it.

Warm up >=30 s. Start Validation on all three devices. Keep them stationary for >=330 s; the app holds the validation screen awake. End all three runs. Each selected run must report `snapshot_frozen=true`, `elapsed_ms>=300000`, `acceptance_duration_eligible=true`, `environment_valid=true`, `usable_metric_range_uptime_percent>=90`, `geometry_2d_uptime_percent>=90`, `peer_expire_delta=0`, and `recovery_attempt_delta<=3`.

Export each completed long run as `<device>_run_long_export1.json`. Do not take screenshots. Leave the apps running >=180 s and export the SAME selected long run again as `<device>_run_long_export2.json`. Then create and end one short diagnostic run <300 s (it must have `acceptance_duration_eligible=false`), reselect the original long run, and export it as `<device>_run_long_after_short_run.json`. These three JSONs prove frozen-snapshot immutability and run-history selection.

For targeted starvation/recovery evidence, if a natural isolated peer starvation occurs, do not disturb the other peer. The JSON timeline must identify `PEER_STARVATION`, target `peer_id`, `recovery_generation`, and terminal result. A `RECOVERY_SUCCESS` is valid only when `FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY.peer_id` equals the target peer. Full-cohort recovery remains a separate trigger and all recoveries share the global 3-attempts/5-min budget.

## 3. Validate the Android JSON evidence on Ubuntu, WSL or Windows
Extract `validators-dev12.zip` into a directory with the nine exported JSON files. Run:

```bash
python3 validate_dev12_hard_gates.py pixel10_run_long_export1.json
python3 validate_dev12_hard_gates.py pixel7_run_long_export1.json
python3 validate_dev12_hard_gates.py lenovo_run_long_export1.json
python3 validate_peer_starvation_recovery.py pixel10_run_long_export1.json
python3 validate_peer_starvation_recovery.py pixel7_run_long_export1.json
python3 validate_peer_starvation_recovery.py lenovo_run_long_export1.json
python3 validate_snapshot_immutability.py pixel10_run_long_export1.json pixel10_run_long_export2.json pixel10_run_long_after_short_run.json
python3 validate_snapshot_immutability.py pixel7_run_long_export1.json pixel7_run_long_export2.json pixel7_run_long_after_short_run.json
python3 validate_snapshot_immutability.py lenovo_run_long_export1.json lenovo_run_long_export2.json lenovo_run_long_after_short_run.json
python3 build_acceptance_report.py --device pixel10=pixel10_run_long_export1.json --device pixel7=pixel7_run_long_export1.json --device lenovo=lenovo_run_long_export1.json --out acceptance_report.json
```

All validators must exit 0. Keep `acceptance_report.json` plus the nine device exports as the complete diagnostic evidence set. If tape distances are collected, fill `ground-truth-template.json` outside the app and use `calculate_accuracy_report.py` only as an informative COARSE-accuracy report; it is not a hard gate.

## 4. Android compatibility artifacts
`body-finder-ruview-legacy-minsdk21.apk`: install on a compatible older Android, launch it and verify startup/capability diagnostics. It is a compatibility smoke artifact, not a substitute for the three-device dev-12 acceptance run.

`body-finder-ruview.aab`: verify its checksum. For local bundle smoke testing, use your installed Google bundletool to generate/install an APK set from this AAB; the authoritative field acceptance remains `BodyFinder-dev12-universal.apk` because it is directly reproducible from the release asset.

## 5. Linux artifacts
For `body-finder-node-linux-x86_64.tar.gz`:

```bash
tar -xzf body-finder-node-linux-x86_64.tar.gz
chmod +x body-finder-node
./body-finder-node --help
./body-finder-node --node ubuntu-test --session body-finder-lab --calibrate 10 --record ubuntu-node.jsonl
```

Stop with Ctrl+C after observing startup/fabric output and confirm `ubuntu-node.jsonl` was created. For the Debian package, run `sudo dpkg -i body-finder-node-linux-x86_64.deb`, then `body-finder-node --help`. The node accepts no manual coordinates; normal geometry is automatic.

## 6. Windows / WSL artifact
Extract `body-finder-node-windows-x86_64.zip` in native Windows PowerShell and run:

```powershell
.\body-finder-node.exe --help
.\body-finder-node.exe --node windows-test --session body-finder-lab --calibrate 10 --record windows-node.jsonl
```

Stop with Ctrl+C and confirm `windows-node.jsonl` exists. WSL should test the Linux tar/deb artifact, not the Windows `.exe`.

## 7. iOS simulator artifact
On macOS, unzip `body-finder-ruview-ios-simulator.zip`, boot an iOS Simulator, install the contained `.app` with `xcrun simctl install booted <path-to-app>`, and launch it from the simulator. This is a build/startup smoke test only: simulator BLE hardware cannot replace the physical Android acceptance test.

## 8. Validator regression fixtures and release metadata
Extract `fixtures-dev12.zip` and use it with the validators to reproduce healthy, isolated-starvation, wrong-peer-return, timeout, cooldown, attempt-4 and full-cohort cases. `body-finder-validation-tools.zip` is the same validation kit for archival use. Preserve `DEV12_FROZEN_TRUTH.md`, `validation-run-snapshot-v2.schema.json`, calibration files, capability matrix, SBOM, protocol version, model manifest and `release-manifest.json` with the test evidence.

Final acceptance is based on the three physical Android long-run JSONs and validator outputs. Screenshots are optional visual material only and are never required for diagnosis or acceptance.
