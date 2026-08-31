# TESTING DEV20.8

Engineering G0-G9 are automated. Physical G10-G12 remain PENDING until fresh evidence is collected. JSON is authoritative; screenshots are not required.

## G10 — 6 JSON smoke
1. Verify `SHA256SUMS.txt`, then install `BodyFinder-dev20.8-universal.apk` on Pixel 10 Pro, Pixel 7 Pro and Lenovo TB-J606L.
2. Clean session; Wi-Fi, Bluetooth and required Location ON; Battery Saver OFF; screens ON; app foreground.
3. Wait for exactly 2 peers/device and cohort=3.
4. On the elected coordinator only, calibrate EMPTY. Continue only when all devices show the same calibration id/hash/generation/topology and ACK 3/3.
5. Select `SMOKE_CAL_EMPTY`, Start, keep area empty and nodes still for 90–120 s, End/export one JSON per device.
6. Without recalibration or moving nodes select `HUMAN_MOVING`, Start, move one person for 90–120 s, End/export one JSON per device.
7. Put the six JSON beside `validators-dev20.8.zip`; run `python3 validation/analysis/validate_dev20_8_smoke.py *.json --output dev20.8-smoke-go-no-go.json`. GO requires exit 0 and `final_go=true`.
8. Any failure: STOP and share only the six JSON + verdict. Do not run G11 and do not take screenshots.

## G11 — only after G10 GO
Two independent calendar days × 9 scenarios × 3 devices = 54 fresh JSON; every scenario >=330 s: EMPTY_CAL, EMPTY_TEST, HUMAN_STATIONARY_CENTER, HUMAN_MOVING, HUMAN_NEAR_LENOVO, HUMAN_NEAR_PIXEL10, HUMAN_NEAR_PIXEL7, HUMAN_OUTSIDE, NON_HUMAN_MOTION. Run packaged campaign validator. Required: recall>=0.90, specificity>=0.85, healthy indeterminate<=0.10, stationary recall>=0.80, moving recall>=0.90, exact peer and Android↔CLI parity, all transport/artifact/calibration/authority/snapshot gates green.

`human_localization_validated=false`, `rescue_use_validated=false`, and `dev21_blocked=true` until independent G12 returns GO.
