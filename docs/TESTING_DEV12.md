# TESTING DEV-12 (JSON-only evidence)

## Android 3-device acceptance
1. Install the same `BodyFinder-dev12-universal.apk` on Pixel 10 Pro, Pixel 7 Pro and Lenovo TB-J606L and verify the APK SHA-256 against `SHA256SUMS.txt`.
2. Enable Bluetooth; disable Battery Saver; Lenovo Location ON. Open Expert on all three and start the same session. Wait >=30 s until each device sees 2 expected peers and acquisition is `FILTERED_PRIMARY` / `MANUFACTURER_FILTERED`.
3. Place the three devices motionless in a triangle, each separation 0.5-5.0 m. Record tape distances separately for accuracy only.
4. Start Validation Run on all three. Keep them motionless for >=330 s. The app keeps the screen awake while the run is active.
5. End the run. Export the selected long-run JSON once per device. **No screenshots are required.** Each JSON contains build/device/preflight/environment, acquisition strategy, per-peer health/starvation/recovery, full causal timeline, geometry/fusion snapshot, hard-gate metrics and safety truth.
6. Optional immutability check: wait >=180 s, export the same selected run again; create/end a short run; reselect the long run and export again.
7. Put the 3 primary JSON files in one folder and run:
   `python validate_dev12_hard_gates.py <json>` for each,
   `python validate_peer_starvation_recovery.py <json>` for each, and
   `python build_acceptance_report.py pixel10.json pixel7.json lenovo.json > acceptance_report.json`.

Acceptance requires all 3: elapsed >=300000, eligible=true, environment_valid=true, usable metric >=90%, Geometry2D >=90%, peer_expire_delta=0, recovery_attempt_delta<=3.

## Linux / WSL / Windows
Run the packaged node artifact with `--help` and the repository regression tests. These artifacts do not require screenshot evidence; retain command output only if a platform launch fails.
