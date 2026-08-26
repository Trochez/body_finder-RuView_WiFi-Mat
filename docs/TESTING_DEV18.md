# TESTING DEV18 — RF acquisition / recorder / replay

`dev-18` is a scientific-acquisition release. It does **not** enable human detection/localization and requires **no screenshots**. Share only the exported JSON/JSONL plus generated validator reports.

## 1. Verify release

Download the `dev-18` assets and run:

```bash
sha256sum -c SHA256SUMS.txt
```

Install `BodyFinder-dev18-universal.apk` on the 3 Androids. Ubuntu/Windows use the packaged node/science binaries. iOS simulator is build smoke only; a physical iPhone campaign is still required by the future cross-platform gate.

## 2. Re-run frozen dev-17 non-regression gate

```bash
python3 validators-dev18/validate_dev17_baseline.py validation/baselines/dev17/acceptance-summary.json
```

Expected: `"pass": true`.

## 3. Ubuntu native RF session

Keep the target area empty first:

```bash
chmod +x body-finder-rf-recorder-linux-x86_64 body-finder-replay-linux-x86_64 body-finder-validate-session-linux-x86_64
./body-finder-rf-recorder-linux-x86_64 --session empty-01 --node ubuntu-01 --duration 60 --output empty-01.jsonl --manifest empty-01.manifest.json
./body-finder-validate-session-linux-x86_64 --manifest empty-01.manifest.json --input empty-01.jsonl > empty-01.validation.json
./body-finder-replay-linux-x86_64 --input empty-01.jsonl > empty-01.replay-a.json
./body-finder-replay-linux-x86_64 --input empty-01.jsonl > empty-01.replay-b.json
```

The two `deterministic_digest` values must be identical. Repeat once with a person moving in the scan zone, but **do not interpret the difference as validated human detection**.

## 4. Android 3-node acquisition

Use the same physical setup that passed dev-17: Pixel 7 Pro + Pixel 10 Pro + Lenovo TB-J606L, same LAN/Bluetooth, non-collinear triangle, foreground, Battery Saver OFF. On each phone:

1. Calibrate empty scene.
2. Start a validation run and keep all three stationary for >=330 s.
3. End the run and use **Share complete test JSON**.
4. Save one JSON per device. The JSON itself is the evidence; no screenshot is accepted or needed.

This campaign is for RF dataset capture and dev-17 regression only. `humanScanningEnabled=false` remains correct.

## 5. Windows / WSL semantics

Run the Windows recorder from native Windows. On WSL, direct RF may report `UNSUPPORTED`; that is a PASS for capability-truth semantics and WSL remains compute/replay only.

## 6. What to send back

Send: 3 Android JSONs, Ubuntu `*.jsonl` + `*.manifest.json` + validation/replay JSONs, and (if available) native-Windows equivalents. These are sufficient for the next dev-19 human/no-human dataset analysis; screenshots are unnecessary.
