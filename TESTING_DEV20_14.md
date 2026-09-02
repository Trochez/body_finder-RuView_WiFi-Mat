# TESTING dev-20.14 — 3-node physical G10

Screenshots are **not required**. The only acceptance evidence is JSON.

## Devices

Use the same three Android devices: Pixel 10 Pro, Pixel 7 Pro and Lenovo. Keep all three on the same local network, Bluetooth enabled, app foreground, screen on and battery saver off. Place the three devices in a non-collinear triangle with each required BLE baseline inside the calibrated **0.5–5.0 m** domain. Do not enter node coordinates manually.

## 1. Install the exact release

On each Android device:

1. Uninstall any previous Body Finder APK and remove stale app state.
2. Install `BodyFinder-dev20.14-universal.apk` from the `dev-20.14` GitHub prerelease.
3. Confirm the app reports build `0.2.0-experimental.20.14` / report 34.
4. Start the app on device 1, wait about 10 s, start device 2, wait about 10 s, then start device 3.

## 2. Mandatory preflight

Do **not** calibrate or start a 330 s scenario until all three devices simultaneously show:

- `Authority consensus 3/3`;
- identical elected coordinator;
- identical coordinator generation;
- identical authority-view digest;
- 3 positioned nodes;
- `GEOMETRY_2D`.

If any condition fails, on **each** device export `PRE_RUN_DIAGNOSTIC_V1` and stop. Share exactly the three JSONs. Do not use screenshots as evidence.

## 3. SMOKE_CAL_EMPTY

1. Leave the scene empty.
2. On the elected coordinator, start calibration.
3. Require `Calibration ACK 3/3`.
4. Select/issue `SMOKE_CAL_EMPTY` and require `Scenario ACK 3/3`.
5. Start and require `RunStart READY 3/3` / distributed commit.
6. Run for **at least 330 s**.
7. Freeze/end from the coordinator and require `Snapshot READY 3/3`.
8. Export exactly one acceptance JSON from each device: **3 EMPTY JSONs**.

## 4. HUMAN_MOVING

Without moving or recalibrating the three nodes:

1. Select/issue `HUMAN_MOVING` and again require all 3/3 barriers.
2. Start the run and keep a person moving in the sensing area.
3. Run for **at least 330 s**.
4. Freeze/end from the coordinator and require `Snapshot READY 3/3`.
5. Export exactly one acceptance JSON from each device: **3 HUMAN JSONs**.

## 5. Validate G10

Place the six acceptance JSONs in one directory with `validate_dev20_14_g10.py`, then run:

```bash
python3 validate_dev20_14_g10.py *.json --output g10-dev20.14-physical.json
```

PASS requires exactly 6 files: 3 `SMOKE_CAL_EMPTY` + 3 `HUMAN_MOVING`, every run >=330000 ms, Authority/Calibration/Scenario/RunStart/Snapshot all 3/3, and identical authority coordinator/generation/digest across the six exports.

If the validator returns non-zero, G10 remains `NO_GO/PHYSICAL_PENDING`; share `g10-dev20.14-physical.json` plus the six source JSONs. G11/dev21 remain blocked until this validator reports `GO`.

## Optional desktop artifact smoke

Linux/Ubuntu: extract the Linux archive or install the `.deb`, then run `body-finder-node --help` and `body-finder-detector --help`.

Windows/WSL: extract `body-finder-windows-wsl-x86_64.zip` and run the packaged binaries with `--help`. These desktop smoke checks do not replace the Android physical G10 campaign.
