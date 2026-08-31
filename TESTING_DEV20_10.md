# DEV-20.10 — G10 physical smoke

JSON is authoritative; screenshots are not required.

1. Download `BodyFinder-dev20.10-universal.apk`, `validators-dev20.10.zip`, the detector for your OS and `SHA256SUMS.txt`; verify SHA-256.
2. Uninstall/clear old Body Finder state on Pixel 10 Pro, Pixel 7 Pro and Lenovo TB-J606L; install the identical dev20.10 APK.
3. Same LAN; Bluetooth ON; Battery Saver OFF; screens ON; app foreground; Lenovo Location ON if required. Fixed non-collinear triangle, pairwise 0.5–5 m where practical.
4. Wait for exactly 2 current peers/device, no ghosts, RANGE_FRAME TX/RX>0, required frames <=1200 B, oversize=0 and same coordinator/geometry revision/digest.
5. Calibrate EMPTY only on the coordinator; wait for same calibration id/hash/generation/topology and ACK 3/3.
6. Start explicit `SMOKE_CAL_EMPTY` on all three for >=330000 ms; export one JSON/device.
7. Without moving nodes or recalibrating, start explicit `HUMAN_MOVING` on all three for >=330000 ms; export one JSON/device.
8. Confirm JSON internals contain exactly 3 EMPTY + 3 HUMAN. Put all six in `evidence/`.
9. Linux: `python3 validate_dev20_10_smoke.py --evidence-dir evidence --output dev20.10-smoke-go-no-go.json --detector ./body-finder-detector-linux-x86_64`. Windows uses the packaged `.exe`.
10. Continue to G11 only if `g10_go=true`; otherwise STOP and share the six JSON plus verdict JSON.
