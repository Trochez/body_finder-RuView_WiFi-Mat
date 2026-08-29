# TESTING DEV-20.4

Physical acceptance is **PENDING**. Screenshots are not evidence. Use only the six exported JSON files.

## Mandatory smoke — 3 Androids

Devices: Pixel 10 Pro, Pixel 7 Pro, Lenovo TB-J606L. Install `BodyFinder-dev20.4-universal.apk` on all three.

1. Wi-Fi + Bluetooth ON; Battery Saver OFF; screen ON; app foreground; wait until each device sees 2 peers.
2. Keep the three devices fixed in one non-collinear triangle.
3. On the elected coordinator tap **Calibrar escena vacía** with the area EMPTY. Wait until the presence card reports `calibration_state=READY`. Do not move the devices.
4. Start one short validation run on all three while EMPTY, run ~45–60 s, End, export one JSON/device. Name them `pixel-10-smoke_empty.json`, `pixel-7-smoke_empty.json`, `lenovo-smoke_empty.json`.
5. Without recalibrating or moving devices, start another synchronized run; move one person inside the triangle for ~45–60 s; End and export one JSON/device named `*-smoke_human_moving.json`.
6. Put the 6 JSONs beside the validator bundle and detector binary, then run:

```bash
python3 validate_dev20_4_smoke.py \
  pixel-10-smoke_empty.json pixel-7-smoke_empty.json lenovo-smoke_empty.json \
  pixel-10-smoke_human_moving.json pixel-7-smoke_human_moving.json lenovo-smoke_human_moving.json \
  --detector ./body-finder-detector-linux-x86_64 \
  --output smoke-go-no-go.json
```

**GO** only when exit code is 0 and `smoke-go-no-go.json.final_go=true`. The validator requires READY calibration, online 3 nodes/6 links/3 baselines, exact peer decision/digest equality, exact Rust online/offline replay parity and HUMAN_MOVING=`HUMAN_EVIDENCE`.

## Full campaign — only after smoke GO

The builder refuses to run without the signed smoke GO. Collect two independent days, 9 synchronized scenarios/day, 3 devices/scenario, >=330 s each: `EMPTY_CAL`, `EMPTY_TEST`, `HUMAN_STATIONARY_CENTER`, `HUMAN_MOVING`, `HUMAN_NEAR_LENOVO`, `HUMAN_NEAR_PIXEL10`, `HUMAN_NEAR_PIXEL7`, `HUMAN_OUTSIDE`, `NON_HUMAN_MOTION` = **54 fresh JSON**. Any code/parameter/schema change invalidates that TEST set.

`human_localization_validated=false` and `rescue_use_validated=false` remain mandatory.
