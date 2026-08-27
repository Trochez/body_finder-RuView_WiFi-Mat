# TESTING DEV-20 — 3 Android HUMAN / NO-HUMAN campaign

## Goal
Collect reproducible **real** BLE-RSSI evidence on Pixel 10 Pro, Pixel 7 Pro and Lenovo TB-J606L, then generate one machine-readable acceptance report. No screenshots are required.

## 1. Install
Install `BodyFinder-dev20-universal.apk` on the Pixels. If needed on Lenovo, use `body-finder-ruview-legacy-minsdk21.apk`.

On all 3 phones: Wi-Fi/Bluetooth ON, Battery Saver OFF, screens ON, app foreground. Wait until each phone sees the other 2 nodes and acquisition/geometry is healthy.

## 2. Record runs
For every condition, on **all 3 phones**: **Start validation run** → hold the condition for **≥5 min** → **End validation run** → **Share complete test JSON**.

Minimum conditions: `EMPTY_CAL`, `EMPTY_TEST`, `HUMAN_STATIONARY_CENTER`, `HUMAN_MOVING`, `HUMAN_NEAR_NODE`, `HUMAN_OUTSIDE`, and one non-human motion negative control where practical. Use multiple physical sessions/days. Never split adjacent windows from one run between train/test.

## 3. Label externally
Copy `campaign-manifest-template.json` and set each `export`, `ground_truth`, `scenario`, `environment_id`, `day_id`, `calibration_id`, `role`, and `split`. Ground truth stays external to inference. Final acceptance runs use `split=TEST` and `used_for_model_selection=false`.

## 4. Validate
Linux/WSL, Python 3.10+:

```bash
python3 build_dev20_campaign.py --manifest campaign-manifest.json --output dev20-campaign.json
python3 validate_dev20_human_detection.py dev20-campaign.json --engineering-targets --output dev20-acceptance.json
```

PASS requires dev-19 acquisition health, no session leakage, frozen TEST data, and engineering targets **recall ≥90% / specificity ≥85%** in the validated in-room regime. Static/moving and held-out-device metrics are separate. Low-quality evidence must become `INDETERMINATE`; `NO_HUMAN_EVIDENCE` is never proof of absence.

## 5. Return evidence
Send `dev20-acceptance.json`, `dev20-campaign.json`, and the original exported JSON only if deeper diagnosis is needed. Screenshots are optional.

The release also ships fail-closed forward validators for dev-21 localization/uncertainty, dev-22 tracking/clusters, dev-23 capability truth, controlled dev-24 NLOS/mock-debris evaluation, and the aggregate v1 gate. Those gates cannot pass without their required physical evidence.
