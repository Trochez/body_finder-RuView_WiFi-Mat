# TESTING DEV15 — telemetry/tooling smoke

No screenshots. Return only exported JSON files plus the generated reports.

## 1. Verify the release
Download all assets from prerelease `dev-15` into one folder.

Ubuntu/WSL:
```bash
sha256sum -c SHA256SUMS.txt
python3 -c "import json; x=json.load(open('release-verification.json')); assert x['pass'] and x['redownload_verified']"
```

## 2. Offline validator self-test — no hardware
```bash
unzip -q validators-dev15.zip -d validators-dev15
unzip -q fixtures-dev15.zip -d fixtures-dev15
python3 validators-dev15/test_dev15_tooling.py
```
Expected final line: `DEV15_TOOLING_MATRIX_PASS`.

## 3. Android directed smoke only
Because dev15 changes Android telemetry/export metadata, install the same `BodyFinder-dev15-universal.apk` on **Pixel 10 Pro** and **Pixel 7 Pro**. Do **not** repeat the 330 s × 3 dev14 campaign. Keep Bluetooth ON, Battery Saver OFF, screen ON and Body Finder foreground.

On each phone: start a validation run; induce one peer-starvation recovery without disabling Bluetooth/app (temporarily attenuate/separate the peer, then restore it); wait until recovery completes; end the run; Share JSON. Share the same frozen run a second time, then create one 45–60 s short run, reselect the original long run and Share it again.

The JSON itself must identify `LONG_1`, `LONG_2`, `SHORT`, `LONG_POST_SHORT`; filenames are not diagnostic inputs. Required recovery evidence: `RECOVERY_REQUESTED -> FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY -> RECOVERY_SUCCESS`, target peer correct, global/per-peer FIRST_VALID counters consistent, `snapshot_frozen=true`, and unchanged frozen snapshot on re-export.

## 4. Validate exported evidence
Put all exports in `evidence/`:
```bash
python3 validators-dev15/validate_dev15_acceptance.py --evidence-dir evidence --output acceptance_report.json
python3 validators-dev15/calculate_accuracy_report.py --ground-truth GROUND_TRUTH_TEMPLATE.json --evidence-dir evidence --output accuracy_report.json
```
For this directed smoke, edit only the measured distances in `GROUND_TRUTH_TEMPLATE.json` if three-device evidence was collected. Accuracy is informational only and never changes calibration.

## 5. Desktop artifacts
Ubuntu/WSL: extract `body-finder-node-linux-x86_64.tar.gz` and run `./body-finder-node --help`. Windows: extract `body-finder-node-windows-x86_64.zip` and run `./body-finder-node.exe --help`. The iOS simulator ZIP is build-only.

Send back: exported JSONs, `acceptance_report.json`, `accuracy_report.json`. No screenshots.
