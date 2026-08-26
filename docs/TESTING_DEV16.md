# TESTING_DEV16

## 1. Verify/install
Verify `BodyFinder-dev16-universal.apk` against `SHA256SUMS.txt`, then install the same APK on Pixel 10 Pro and Pixel 7 Pro. Keep Bluetooth ON, permissions granted, Battery Saver OFF, screen ON, app foreground and field service RUNNING. No screenshots are required.

## 2. Directed smoke (2 phones)
On each phone: run LONG >=330 s -> export `LONG_1`; export the same run again as `LONG_2`; start SHORT immediately for 45–75 s -> export `SHORT`; reselect original LONG -> export `LONG_POST_SHORT`. Total: 8 JSON. Across the campaign provoke >=1 complete `PEER_STARVATION` targeted recovery (only one phone is sufficient).

Put the 8 JSON in `evidence-directed/` and run:
```bash
unzip validators-dev16.zip -d validators-dev16
python3 validators-dev16/validate_dev16_directed_smoke.py --evidence-dir evidence-directed --output directed_smoke_report.json
```
PASS requires no unfiltered >10000 ms, no probe >15000 ms, rolling max <=3, each LONG ends FILTERED_PRIMARY with no active recovery, event/counter/summaries consistent, immutable LONG history, immediate LONG->SHORT and valid environment. Target misses within hard limits are warnings.

## 3. Three-device continuity
Pixel 10 Pro + Pixel 7 Pro + Lenovo TB-J606L: one simultaneous LONG >=330 s; export one LONG JSON per device into `evidence-3node/`. Run:
```bash
python3 validators-dev16/validate_dev16_acceptance.py --evidence-dir evidence-3node --output acceptance_report.json
```
Expected: two remote peers, all-expected-peer metric uptime >=90%, geometry 2D >=90%, peer_expire_delta=0, environment valid, rolling budget <=3 and hard deadlines PASS. Accuracy/recalibration and screenshots are not required.

After hardware PASS, share the 8 directed JSON + 3 three-node JSON + both generated reports. CI intentionally leaves `final_go=false` until this physical evidence exists.
