# TESTING DEV15 — directed two-device telemetry/tooling smoke

No screenshots are required. Return only exported JSON files plus the generated directed-smoke report.

## 1. Download and verify the release
Download **all** assets from prerelease `dev-15` into one folder.

Ubuntu/WSL:
```bash
sha256sum -c SHA256SUMS.txt
python3 -c "import json; x=json.load(open('release-verification.json')); assert x['pass'] and x['checksums_verified'] and x['redownload_verified']"
```
Expected: every checksum prints `OK`. `physical_smoke_status` remains `PENDING_USER_HARDWARE` until the real-device smoke is performed.

## 2. Offline validator self-test — no hardware
```bash
unzip -q validators-dev15.zip -d validators-dev15
unzip -q fixtures-dev15.zip -d fixtures-dev15
python3 validators-dev15/test_dev15_tooling.py
```
Expected final line: `DEV15_TOOLING_MATRIX_PASS`.

## 3. Install the Android build
Use **the same** `BodyFinder-dev15-universal.apk` on Pixel 10 Pro and Pixel 7 Pro. USB is not required; install by your preferred transfer method. If ADB is available:
```bash
adb install -r BodyFinder-dev15-universal.apk
```
`body-finder-ruview.aab` is a store/distribution artifact, not the APK for this smoke. `body-finder-ruview-legacy-minsdk21.apk` is only the legacy compatibility build.

On both phones: Bluetooth ON; Battery Saver OFF; screen ON; Body Finder foreground; grant requested Bluetooth/Nearby Devices permissions. Do not disable Bluetooth or force-stop/background the app during recovery.

Before starting, each phone must see exactly **one remote BLE peer**. In the exported/preflight diagnostics this corresponds to `expected_ble_peer_count: 1` and `expected_ble_peers_ready: true`.

## 4. Directed physical smoke — exactly one LONG + one SHORT per phone
Do **not** repeat the old 330 s × 3 dev14 campaign.

1. Open Body Finder on both phones and wait until the other phone appears as the remote peer and preflight is ready.
2. Start a validation run on both phones.
3. Keep the LONG run active for at least **300 s** (300–330 s recommended).
4. During that LONG run, induce one peer-starvation event by temporarily separating/attenuating one phone enough to lose usable peer evidence. Do not turn Bluetooth off and do not close the app.
5. Restore normal proximity and wait for recovery to complete.
6. After the LONG run reaches at least 300 s, end it on both phones.
7. On each phone, Share JSON from that frozen LONG run once (`LONG_1`), then Share the **same frozen run again** (`LONG_2`).
8. Start a new **45–60 s** validation run, end it and Share JSON (`SHORT`).
9. Reselect the original LONG run and Share it again (`LONG_POST_SHORT`).

Expected total from two phones: **8 exported JSON files**. The JSON metadata, not the filename, must identify `LONG_1`, `LONG_2`, `SHORT`, and `LONG_POST_SHORT`.

Required recovery evidence inside the LONG JSON: `RECOVERY_REQUESTED -> FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY -> RECOVERY_SUCCESS`; correct target peer; global/per-peer FIRST_VALID counters consistent; `snapshot_frozen=true`; and the same frozen LONG snapshot unchanged across re-exports.

## 5. Validate the two-device smoke
Create an `evidence/` folder containing only the 8 exported app JSON files, then run:
```bash
python3 validators-dev15/validate_dev15_directed_smoke.py \
  --evidence-dir evidence \
  --output directed_smoke_report.json
```
Expected: top-level `"pass": true` and `"mode": "DIRECTED_TWO_DEVICE_SMOKE"`.

This directed smoke is intentionally **not equivalent to full 3-device acceptance**. With two nodes there is only one pairwise edge, so 2D geometry is not observable. The full `validate_dev15_acceptance.py` campaign remains a separate 3-device validation path and is not required for this post-dev14 delta smoke.

Accuracy is informational only. For this two-phone smoke, leave `GROUND_TRUTH_TEMPLATE.json` with `"pairs_m": []` unless you actually measure the Pixel-to-Pixel distance with a tape. If measured, add only the real pair, for example:
```json
{"a":"pixel-10-pro","b":"pixel-7-pro","distance_m":3.07}
```
Then optionally run:
```bash
python3 validators-dev15/calculate_accuracy_report.py \
  --ground-truth GROUND_TRUTH_TEMPLATE.json \
  --evidence-dir evidence \
  --output accuracy_report.json
```
With no measured pairs the report has `pair_count: 0`; accuracy never changes calibration automatically.

## 6. Desktop/build artifacts
Ubuntu/WSL:
```bash
tar -xzf body-finder-node-linux-x86_64.tar.gz
chmod +x body-finder-node
./body-finder-node --help
```
Optional Debian package check:
```bash
sudo dpkg -i body-finder-node-linux-x86_64.deb
body-finder-node --help
```

Windows PowerShell:
```powershell
Expand-Archive .\body-finder-node-windows-x86_64.zip -DestinationPath .\dev15-win
.\dev15-win\body-finder-node.exe --help
```

`body-finder-ruview-ios-simulator.zip` is a CI/build artifact for iOS Simulator; no physical iPhone validation is required by this directed dev15 smoke.

## 7. Evidence to send back
Send only:
- the 8 exported Android JSON files;
- `directed_smoke_report.json`;
- `accuracy_report.json` only if you measured a real Pixel-to-Pixel distance.

No screenshots are needed for diagnosis or acceptance of the directed smoke.
