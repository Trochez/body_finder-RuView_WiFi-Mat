# TESTING_DEV12

## 1. Install
Install `body-finder-ruview-universal.apk` on the three Android devices. Verify all three APK files have the same SHA-256 from `SHA256SUMS`. Keep the same session (`body-finder-lab`).

## 2. Arrange the devices
Use Pixel 10 Pro, Pixel 7 Pro and Lenovo TB-J606L, stationary, in a 0.5-5.0 m triangle. Measure the three pairwise distances with a tape and save them separately for the optional accuracy report. Do **not** enter ground truth into the app.

## 3. Preflight on each Android
Open Expert and verify `Validation preflight.ready=true`: Bluetooth ON, Battery Saver OFF, screen ON, app foreground, foreground service RUNNING, two expected BLE peers, `FILTERED_PRIMARY`, `MANUFACTURER_FILTERED`, `hardware_filter_count>0`; on Android <=11 Location must be ON.

## 4. Acceptance run
Warm up >=30 s. Start Validation on all three devices. The app requests keep-awake while the run is active. Leave devices stationary for >=330 s. End each run. `acceptance_duration_eligible` must be true.

## 5. Export evidence — JSON only
Export the selected long run as `*_run_long_export1.json`. Leave the app running >=180 s, export the **same** run as `*_run_long_export2.json`. Create a short diagnostic run (<300 s), end it (expected `acceptance_duration_eligible=false`), reselect the long run, export `*_run_long_after_short_run.json`. **Screenshots are not required.** Each JSON contains preflight, environment, BLE per-peer state, starvation/recovery causality, system-ranging state, frozen geometry/fusion/graph data and a self-diagnostic gate summary.

## 6. Validate on Ubuntu / WSL / Windows
Unzip `validators-dev12.zip`, then run:

```bash
python3 build_acceptance_report.py --device pixel10=pixel10_run_long_export1.json --device pixel7=pixel7_run_long_export1.json --device lenovo=lenovo_run_long_export1.json --out acceptance_report.json
python3 validate_snapshot_immutability.py pixel10_run_long_export1.json pixel10_run_long_export2.json pixel10_run_long_after_short_run.json
python3 validate_snapshot_immutability.py pixel7_run_long_export1.json pixel7_run_long_export2.json pixel7_run_long_after_short_run.json
python3 validate_snapshot_immutability.py lenovo_run_long_export1.json lenovo_run_long_export2.json lenovo_run_long_after_short_run.json
```

Hard acceptance per device: frozen snapshot; elapsed >=300000 ms; duration eligible; environment valid; usable metric >=90%; Geometry2D >=90%; peer_expire_delta=0; recovery attempts <=3. Accuracy remains `COARSE` and informative.
