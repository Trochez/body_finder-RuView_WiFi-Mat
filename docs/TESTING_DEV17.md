# TESTING DEV17

Only one new physical campaign is required. Do **not** repeat the Pixel 7/Pixel 10 four-stage dev16 history campaign and do not take screenshots.

## 1. Verify release

Download all `dev-17` assets and run:

```bash
sha256sum -c SHA256SUMS.txt
```

Use exactly `BodyFinder-dev17-universal.apk` on all three Android devices.

## 2. Prepare 3 nodes

Devices: Pixel 10 Pro, Pixel 7 Pro, Lenovo TB-J606L. Same LAN; Bluetooth ON; permissions granted; Battery Saver OFF; screen ON; app foreground; foreground service RUNNING; Lenovo Location ON if Android requires it. Place stationary in a non-collinear triangle, every pair `0.5–5.0 m`.

Wait until **each device shows 2 expected BLE peers** and `preflight ready=true`.

## 3. Run

1. Start LONG on all three as simultaneously as practical.
2. Keep all three stationary for **>=330 s**.
3. End all three.
4. Export exactly one `LONG_1` JSON per device.
5. Put only those three JSON files in `evidence-3node/`.

## 4. Validate

```bash
unzip validators-dev17.zip -d validators-dev17
python3 validators-dev17/validate_dev17_acceptance.py \
  --evidence-dir evidence-3node \
  --output acceptance_3node_report.json
```

PASS requires per node: build `0.2.0-experimental.17`, protocol `2`, schema `4`, 2 expected peers, metric continuity `>=90%`, Geometry2D `>=90%`, `peer_expire_delta=0`, frozen preflight/environment valid, rolling recoveries `<=3/5min`, no hard timing breach, end `FILTERED_PRIMARY`, no active recovery.

Then create the final report:

```bash
python3 validators-dev17/build_dev17_final_report.py \
  --baseline dev16_directed_baseline_report.json \
  --three-node acceptance_3node_report.json \
  --release-verification release-verification.json \
  --output dev17_final_acceptance_report.json
```

`final_go=true` only when baseline dev16, CI/release SHA, forbidden-runtime-diff and the new 3-node report all pass. Share the 3 LONG JSONs plus both generated reports; no screenshots are needed.
