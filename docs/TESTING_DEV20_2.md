# TESTING DEV-20.2

Release target: `dev-20.2 / 0.2.0-experimental.20.2`  
Safety: experimental only; localization and rescue-use remain unvalidated. Screenshots are not required.

## 1. Assets

Use `BodyFinder-dev20.2-universal.apk` on Pixel 10 Pro, Pixel 7 Pro and Lenovo TB-J606L. `body-finder-ruview-legacy-minsdk21.apk` is only a compatibility artifact. Validators are in `validators-dev20.2.zip`.

Verify downloads first:

```bash
sha256sum -c SHA256SUMS.txt
```

## 2. 30-second sharing smoke test

On each Android: install APK, open app, grant requested Bluetooth/location/nearby permissions, Wi-Fi ON, Bluetooth ON, Battery Saver OFF, screen ON, app foreground. Confirm all three nodes see the other two. Start a short validation run for 15–30 s, End, tap **Share complete test JSON**, save the `.json` file and verify it opens as JSON. Do this on all three devices before long runs.

Required in each shared file:

```text
build = 0.2.0-experimental.20.2
json_self_contained = true
screenshots_required = false
evidence_contract.schema = dev20.2-self-contained-json-evidence-v5
human_localization_validated = false
rescue_use_validated = false
```

## 3. Physical layout

Keep the three devices fixed as a non-collinear triangle for a complete scenario group. Do not move devices during one run. Use the same LAN/session; all three apps foreground; Battery Saver OFF; screens ON. Wait until each device sees two BLE peers before Start.

Acceptance run: **minimum 330 s**, operational target **~360 s**.

## 4. Two-day campaign

Run all nine groups on Day 1, then repeat all nine on Day 2 with a new empty-scene calibration. For every group run the three Android validation runs concurrently and export one frozen JSON from each device.

| Scenario | Truth | Role |
|---|---|---|
| EMPTY_CAL | EMPTY | CALIBRATION |
| EMPTY_TEST | EMPTY | OBSERVATION |
| HUMAN_STATIONARY_CENTER | HUMAN_PRESENT | OBSERVATION |
| HUMAN_MOVING | HUMAN_PRESENT | OBSERVATION |
| HUMAN_NEAR_LENOVO | HUMAN_PRESENT | OBSERVATION |
| HUMAN_NEAR_PIXEL10 | HUMAN_PRESENT | OBSERVATION |
| HUMAN_NEAR_PIXEL7 | HUMAN_PRESENT | OBSERVATION |
| HUMAN_OUTSIDE | EMPTY | OBSERVATION |
| NON_HUMAN_MOTION | EMPTY | OBSERVATION |

Expected total: `9 scenarios × 2 days × 3 Androids = 54 JSON`.

Do not tune detector parameters after starting final TEST collection. Any code/parameter change invalidates the TEST set.

## 5. Folder layout

```text
evidence-dev20.2/
  day1/
    EMPTY_CAL/{pixel10.json,pixel7.json,lenovo.json}
    EMPTY_TEST/{...}
    HUMAN_STATIONARY_CENTER/{...}
    HUMAN_MOVING/{...}
    HUMAN_NEAR_LENOVO/{...}
    HUMAN_NEAR_PIXEL10/{...}
    HUMAN_NEAR_PIXEL7/{...}
    HUMAN_OUTSIDE/{...}
    NON_HUMAN_MOTION/{...}
  day2/
    ...same nine groups...
```

## 6. Manifest

Create `campaign-manifest.json` with one row per export (54 rows). Reuse one `campaign_scenario_id` for the three exports belonging to the same physical group. Day-specific `EMPTY_CAL` and all observations from that day use the same `calibration_id`. Final observations must be `split=TEST` and `used_for_model_selection=false`.

Example row:

```json
{
  "export":"evidence-dev20.2/day1/HUMAN_MOVING/pixel10.json",
  "campaign_scenario_id":"day1::HUMAN_MOVING",
  "day_id":"day1",
  "environment_id":"room-A-day1",
  "scenario":"HUMAN_MOVING",
  "ground_truth":"HUMAN_PRESENT",
  "split":"TEST",
  "role":"OBSERVATION",
  "calibration_id":"day1-empty-cal",
  "used_for_model_selection":false
}
```

For the Day-1 EMPTY_CAL rows use `campaign_scenario_id=day1::EMPTY_CAL`, `ground_truth=EMPTY`, `role=CALIBRATION`, `calibration_id=day1-empty-cal`. Equivalent for Day 2.

## 7. Build campaign and validate

Linux/Ubuntu/WSL:

```bash
unzip validators-dev20.2.zip -d validators-dev20.2
python3 validators-dev20.2/validation/analysis/build_dev20_campaign.py \
  --manifest campaign-manifest.json \
  --output dev20.2-campaign.json

python3 validators-dev20.2/validation/analysis/validate_dev20_human_detection.py \
  dev20.2-campaign.json \
  --final-test \
  --output dev20.2-acceptance.json
```

PASS requires exit code 0 plus:

```text
baseline_regression = PASS
physical_acceptance = PASS
final_go = true
recall >= 0.90
specificity >= 0.85
indeterminate_rate <= 0.10
stationary-human recall >= 0.80
moving-human recall >= 0.90
human_localization_validated = false
rescue_use_validated = false
```

If topology/acquisition is weak, the detector must return `INDETERMINATE`; weak evidence must never be converted to `NO_HUMAN_EVIDENCE`.

## 8. What to send back

Send only:

1. the 54 JSON exports;
2. `campaign-manifest.json`;
3. `dev20.2-campaign.json`;
4. `dev20.2-acceptance.json`.

No screenshots are needed. Do not start dev-21 unless `dev20.2-acceptance.json` has `physical_acceptance=PASS` and `final_go=true`.
