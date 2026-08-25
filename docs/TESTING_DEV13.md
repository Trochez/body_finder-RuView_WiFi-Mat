# TESTING_DEV13

No screenshots are required. Every test artifact must produce/share JSON or JSONL containing its own diagnostic truth.

## 1. Verify release
Download all assets from `dev-13`, then:

```bash
sha256sum --check SHA256SUMS.txt
python3 -m json.tool release-verification.json >/dev/null
python3 validation-kit/validate_release_manifest.py release-manifest.json
```

Use the same `body-finder-ruview-universal.apk` on Pixel 10 Pro, Pixel 7 Pro and Lenovo TB-J606L.

## 2. Three-Android acceptance
1. Put the three devices stationary in a non-collinear triangle, each pair 0.5–5.0 m. Record tape distances in `ground-truth-template.json` only; never enter coordinates into the app.
2. Bluetooth ON, Battery Saver OFF, screen ON, app foreground, same session. Wait until each shows >=2 BLE peers and preflight `ready=true`.
3. Start Validation on all three; keep stationary >=330 s; End Validation.
4. Export the selected long run from each device as `*_run_long_export1.json`.
5. Leave apps alive >=180 s without starting another run; export the same long run as `*_run_long_export2.json`.
6. On each device create one short run <300 s; then reselect the original long run and export `*_run_long_after_short_run.json`.
7. Run:

```bash
unzip validators-dev13.zip -d validation-kit
python3 validation-kit/validate_dev13_hard_gates.py pixel10_run_long_export1.json
python3 validation-kit/validate_dev13_hard_gates.py pixel7_run_long_export1.json
python3 validation-kit/validate_dev13_hard_gates.py lenovo_run_long_export1.json
python3 validation-kit/validate_snapshot_immutability.py pixel10_run_long_export1.json pixel10_run_long_export2.json pixel10_run_long_after_short_run.json
python3 validation-kit/validate_snapshot_immutability.py pixel7_run_long_export1.json pixel7_run_long_export2.json pixel7_run_long_after_short_run.json
python3 validation-kit/validate_snapshot_immutability.py lenovo_run_long_export1.json lenovo_run_long_export2.json lenovo_run_long_after_short_run.json
python3 validation-kit/validate_preflight_snapshot.py pixel10_run_long_export1.json
python3 validation-kit/validate_environment_authorization.py
python3 validation-kit/build_acceptance_report.py --device pixel10=pixel10_run_long_export1.json --device pixel7=pixel7_run_long_export1.json --device lenovo=lenovo_run_long_export1.json --out acceptance_report.json --md acceptance_report.md
python3 validation-kit/calculate_accuracy_report.py --ground-truth ground-truth-template.json --export pixel10_run_long_export1.json --export pixel7_run_long_export1.json --export lenovo_run_long_export1.json > accuracy_report.json
```

PASS requires 3/3 frozen schema-v3 snapshots, >=300 s, `environment_valid=true`, preflight primary/filtered, usable metric and Geometry2D >=90%, peer expiry=0, recovery attempts<=3, unauthorized strategy violations=0, plus the recovery/timeline/geometry validators.

## 3. Ubuntu / WSL
Extract the Linux tarball (or install the `.deb`) and run:

```bash
./body-finder-node --node ubuntu --session body-finder-lab --calibrate 10 --record ubuntu-node.jsonl
```

On WSL use the same Linux binary. Stop with Ctrl+C. `ubuntu-node.jsonl` is the evidence: each line includes build/release, capabilities, geometry state, safety flags and self-diagnostic fields.

## 4. Windows
Extract `body-finder-node-windows-x86_64.zip` and run PowerShell:

```powershell
.\body-finder-node.exe --node windows --session body-finder-lab --calibrate 10 --record windows-node.jsonl
```

`windows-node.jsonl` is the complete evidence; no screenshot is needed.

## 5. iOS simulator
Unzip `body-finder-ruview-ios-simulator.zip`, install/launch the `.app` in an iOS Simulator and confirm it starts. This is a build/smoke artifact; the physical BLE acceptance gate is Android.

Return the nine Android JSON exports, filled ground-truth JSON, `acceptance_report.json`, `acceptance_report.md`, `accuracy_report.json`, plus Linux/WSL/Windows JSONL when those artifacts are tested.
