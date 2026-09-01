# TESTING dev-20.11

1. Install the same `BodyFinder-dev20.11-universal.apk` on Pixel 10 Pro, Pixel 7 Pro and Lenovo TB-J606L. Same LAN; Bluetooth ON; Battery Saver OFF; screens ON; app foreground; Lenovo Location ON if required. Never enter node coordinates manually.
2. Place a fixed non-collinear triangle (every pair 0.5–5 m). Wait for exactly 2 peers/device, range TX/RX >0 and automatic 2D geometry. Calibrate EMPTY **only on the elected coordinator** and wait for calibration ACK 3/3.
3. Coordinator: **ISSUE START EMPTY**. Verify all devices show `SMOKE_CAL_EMPTY`, same digest, ACK 3/3. Start all 3 and keep EMPTY >=330 s. Coordinator presses End once to issue Freeze Prepare; wait SNAPSHOT_READY 3/3; press End again; then end peers after commit. Export one JSON/device.
4. Do not move/recalibrate. Coordinator: **ISSUE START HUMAN_MOVING**. Verify same-digest ACK 3/3. Start all 3, keep one human moving >=330 s, freeze/end identically, export one JSON/device.
5. Put exactly six JSONs in one folder and run: `python3 validation/analysis/validate_dev20_11_smoke.py --evidence-dir <folder> --detector ./body-finder-detector-linux-x86_64 --output g10.json` (Windows: use the `.exe`).

Required: `g10_go=true`; exactly 3 EMPTY + 3 HUMAN; each >=330000 ms; environment valid; peer expiry 0; usable range >=90%; Geometry2D >=90%; control <=900 B; required datagrams <=1200 B; oversize=0; scenario/calibration/freeze 3/3; atomic evidence valid; 3/6/3 authority; exact Android/CLI digest+prediction parity; EMPTY=NO_HUMAN_EVIDENCE; HUMAN=HUMAN_EVIDENCE. Screenshots are unnecessary. If any check fails, stop and share the six JSONs + `g10.json`; do not run G11.
