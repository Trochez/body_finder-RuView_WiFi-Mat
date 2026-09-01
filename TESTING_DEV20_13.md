# TESTING DEV-20.13

## 1. Install
1. Download `BodyFinder-dev20.13-universal.apk` from release `dev-20.13`.
2. Uninstall the previous app on Pixel 10 Pro, Pixel 7 Pro and Lenovo; install the APK cleanly on all three.
3. Put the three Androids on the same field network, enable Bluetooth/location permissions and keep all apps foreground. Do not enter coordinates manually.

## 2. Distributed preflight
1. Start the app in staggered order (about 10 s between devices).
2. On all three verify: `Authority consensus 3/3`, identical coordinator ID and generation, 3 positioned nodes and `GEOMETRY 2D`.
3. Only then calibrate the empty scene on the elected coordinator. Require `Calibration ACK 3/3`.
4. Issue the scenario and require `Scenario ACK 3/3`; press Start and require `RunStart READY 3/3`. All devices must auto-start with the same campaign token.
5. If any gate does not reach 3/3, press **Exportar diagnóstico** on each device and return the 3 `PRE_RUN_DIAGNOSTIC_V1` JSON files. Stop: they are diagnostic only, not G10 evidence.

## 3. G10 physical evidence
1. Run `SMOKE_CAL_EMPTY` for at least **330 s**; freeze/end through the coordinator and require `Snapshot READY 3/3`. Export one acceptance JSON from each device.
2. Without moving/recalibrating nodes, run `HUMAN_MOVING` for at least **330 s** and export the other 3 JSONs.
3. Return exactly 6 JSONs (3 EMPTY + 3 HUMAN). Screenshots are unnecessary.
4. Optional local validation: `python validation/analysis/validate_dev20_13_g10.py <six-json-files> --output g10-dev20.13.json`.

Expected engineering state before these physical files exist: `engineering_go=true`, `g10=PHYSICAL_PENDING`, `g11=BLOCKED`, `dev21_blocked=true`.
