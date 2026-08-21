# Body Finder – RuView experimental.7: BLE metric continuity retest

## Purpose

This is the physical acceptance test for the BLE metric continuity increment after `dev-6` proved that `android-ble-lab-v1` is physically accurate enough for experimental COARSE sensor geometry but did not maintain metric ranges/2D geometry continuously enough.

This test validates **temporal availability**, not a new calibration. Do not repeat the 0.5/1/2/3/5 m campaign. Do not start human-presence, LOS, movement or through-wall tests yet.

The release remains experimental and is **not validated for rescue use**.

---

## 1. Use exactly one experimental.7 release

Use only the newest `dev-*` prerelease whose `release-manifest.json` says:

```text
version = 0.2.0-experimental.7
protocol_version = 2
ble_metric_profile = android-ble-lab-v1
ble_metric_profile_validated = true
ble_metric_profile_physical_confidence = COARSE
ble_metric_valid_distance_min_m = 0.5
ble_metric_valid_distance_max_m = 5.0
ble_valid_rssi_prequeue_filter = true
ble_last_valid_range_holdover = true
ble_holdover_bounded = true
ble_holdover_max_ms = 10000
ble_holdover_sigma_aging = true
human_localization_validated = false
rescue_use_validated = false
```

Do not mix APKs from another release.

Verify `SHA256SUMS` before installation.

---

## 2. Devices

Primary validated Android set:

- Pixel 10 Pro
- Pixel 7 Pro
- Lenovo TB-J606L

All three:

```text
Wi-Fi ON and on the same LAN
Bluetooth ON
Battery Saver OFF
Body Finder foreground/visible
Screen kept ON for this primary run
```

Lenovo / Android <= 11:

```text
Location service ON
```

Do not enter X/Y/Z. Do not enter any physical pair distance into Body Finder.

---

## 3. Install

```bash
adb devices -l
adb -s PIXEL10_SERIAL install -r body-finder-ruview-universal.apk
adb -s PIXEL7_SERIAL install -r body-finder-ruview-universal.apk
adb -s LENOVO_SERIAL install -r body-finder-ruview-universal.apk
```

Use `body-finder-ruview-legacy-minsdk21.apk` only if the universal APK genuinely cannot run on an older Android device. The primary acceptance test targets the universal APK on all three devices.

---

## 4. Pre-flight check

Open **Expert** on every phone.

Verify:

```text
Build: 0.2.0-experimental.7
protocol: 2
Node geometry: AUTO ONLY
manual override: disabled
Human scanning: BLOCKED
```

Calibration must remain:

```text
profile_id: android-ble-lab-v1
validated: true
physical_confidence: COARSE
RSSI@1m: -69.19 dBm
path-loss n: 3.62
valid domain: 0.5–5.0 m
```

Continuity policy must show equivalent values:

```text
fresh_ms: 5000
holdover_max_ms: 10000
hard_expiry_ms: 10000
sigma_aging_m_per_s: 0.15
```

Lifecycle should show:

```text
foreground_service_state = RUNNING
last_error = null
wake_lock_held = true
wifi_lock_held = true
multicast_lock_held = true
```

Stop and export JSON if a device reports Bluetooth disabled, permissions required, foreground service failed, or a lifecycle error.

---

## 5. Physical layout

Use a stationary, clearly non-collinear triangle.

Every physical pair must remain inside the already validated model domain:

```text
0.5 m <= every pair <= 5.0 m
```

Recommended:

```text
Pixel 10 Pro -------- 2–3 m -------- Pixel 7 Pro
       \                              /
        \                            /
        1.5–3 m                1.5–3 m
          \                        /
               Lenovo TB-J606L
```

Requirements:

- phones approximately same height;
- portrait orientation preferred;
- stationary;
- not held in the hand;
- do not deliberately shield antennas with the body;
- do not move devices during the five-minute run.

If you reuse the same layout as the accepted dev-6 geometry test, no new ground-truth file is required. If you move the layout, note the three approximate pair distances after the run only to prove each stayed inside 0.5–5.0 m; those distances are not calibration inputs.

---

## 6. Stabilize before the run

1. Open Body Finder on all three.
2. Wait approximately **30 seconds**.
3. Verify `3 nodes` on each device.
4. Verify two BLE peer identities per device.
5. Verify the scanner is not globally stalled.
6. Preferably wait until the Radar first reaches three metric pair constraints / 2D.

A temporary `ACQUIRING` state is acceptable during startup.

---

## 7. Start the validation run

On all three phones, within a few seconds:

```text
Start validation run
```

Then leave all phones untouched for exactly **5 minutes (300 seconds)**.

Keep:

```text
screens ON
Body Finder foreground
phones stationary
```

Do not press:

```text
Calibrate empty scene
Start human scan
```

Human scanning is intentionally disabled in this build.

---

## 8. Expected temporal behavior

Normal fresh operation:

```text
valid_rssi_sample_count_5s >= 3
range_temporal_state = FRESH
metric_range_source = FRESH_ESTIMATE
```

A brief peer-specific sample gap may produce:

```text
valid_rssi_sample_count_5s < 3
range_temporal_state = HOLDOVER
metric_range_source = LAST_VALID_HOLDOVER
metric_valid = true
last_valid_range_age_ms <= 10000
```

During HOLDOVER:

- distance is the last physically valid in-domain distance;
- its original provenance/timestamp are retained;
- sigma must increase with age;
- the UI must not label it as fresh;
- HOLDOVER can still temporarily support geometry.

If the last valid range exceeds the bounded period, it must disappear from metric geometry. It must never remain usable indefinitely.

---

## 9. Invalid RSSI 127 behavior

`127` may still be observed as an Android invalid/sentinel callback event, but it must be separated from valid RF samples.

Correct diagnostics:

```text
invalid_rssi_sample_count_5s > 0        # allowed if Android emitted invalid callbacks
latest_invalid_rssi_dbm = 127           # allowed diagnostic

valid_rssi_sample_count_5s              # must count only physical RSSI
latest_valid_rssi_dbm                    # must be physical value
median_valid_rssi_dbm                    # must use valid RSSI only
```

Incorrect/failure behavior:

```text
latest_valid_rssi_dbm = 127
median_valid_rssi_dbm = 23
127 inside rssi_samples_dbm
127 contributes to distance estimate
```

The calibration snapshot must contain only valid RSSI values.

---

## 10. Scanner-gap behavior

The app distinguishes global scanner failure from one peer becoming temporarily quiet.

Healthy global scanner:

```text
scan_callback_health = SCANNER_HEALTHY
```

A single peer may show:

```text
peer_gap_state = PEER_TEMPORARILY_NOT_OBSERVED
```

without incrementing scanner restart count.

A scanner restart is justified only by a global callback stall. Isolated peer gaps must not cause scanner restart thrashing.

Record:

```text
scan_restart_delta
scan_callback_health
peer_gap_state per peer
```

---

## 11. Radar expectations

During most of the five minutes the target state is:

```text
3 nodes
3 metric pair edges
GEOMETRY_2D
3/3 nodes positioned
physical confidence = COARSE
```

Radar now also exposes temporal truth:

```text
HOLD count
fresh edge count
holdover edge count
temporal quality
oldest metric edge age
```

Temporal quality may transition among:

```text
FRESH_ONLY
MIXED_FRESH_HOLDOVER
HOLDOVER_DOMINANT
NO_METRIC_GEOMETRY
```

Short `MIXED_FRESH_HOLDOVER` periods are expected and are the purpose of this release.

---

## 12. What must never happen

The following are failures:

```text
RSSI 127 enters the valid queue/median/calibration snapshot
silent clamp to 0.5 m / 5.0 m / 30 m
OUT_OF_DOMAIN enters metric geometry
reciprocal REJECT enters the solver
an expired (>10 s) BLE holdover remains a metric edge
holdover sigma becomes smaller than the original fresh sigma
human scanning becomes enabled
manual coordinate prompt appears
```

If new valid evidence becomes `OUT_OF_DOMAIN_LOW/HIGH`, the previous cached range must not be used to hide it.

---

## 13. End and export

After **5 minutes**:

1. Tap **End validation run** on each phone.
2. Wait about 2 seconds.
3. Capture Radar screenshots.
4. Open Expert and capture the sections listed below.
5. Tap **Share complete test JSON** on each device.

If you accidentally tap Share while the validation run is still active, experimental.7 auto-finalizes the run before creating the export and sets:

```text
export_auto_finalized_validation_run = true
```

The exported `validation_run` should end with:

```text
active = false
ended_wall_ms != null
```

Recommended JSON names:

```text
pixel10_continuity.txt
pixel7_continuity.txt
lenovo_continuity.txt
```

`.json` is also fine; the file extension is not semantically important.

---

## 14. Required screenshots

For each device capture:

```text
[device]_radar.png
[device]_measurement_health.png
[device]_validation_run.png
[device]_ble_diagnostics.png
[device]_reciprocal_fusion.png
```

If one long Expert screenshot clearly contains multiple required sections, fewer image files are acceptable. The JSON is the authoritative evidence.

---

## 15. Exact JSON evidence required

The three full exports must contain enough data to evaluate:

### Validation run

```text
elapsed_ms
peer_expire_delta
address_rebind_delta
scan_restart_delta
all_peer_uptime_percent
ble_evidence_uptime_percent
fresh_metric_range_uptime_percent
usable_metric_range_uptime_percent
holdover_metric_uptime_percent
geometry_2d_uptime_percent
```

### BLE peer diagnostics

```text
raw_sample_count_5s
valid_rssi_sample_count_5s
invalid_rssi_sample_count_5s
raw_sample_count_8s
valid_rssi_sample_count_8s
invalid_rssi_sample_count_8s
latest_valid_rssi_dbm
latest_invalid_rssi_dbm
median_valid_rssi_dbm
range_temporal_state
last_valid_range_age_ms
last_valid_distance_m
last_valid_sigma_m
metric_range_source
peer_gap_state
```

### Graph / fusion

```text
fresh_metric_edge_count
holdover_metric_edge_count
oldest_metric_edge_age_ms
geometry_temporal_quality
metric_edge_pairs
reciprocal fusion state
reciprocal delta
range_age_ms
range_temporal_state
```

---

## 16. Acceptance gates

Primary gates for each five-minute run:

```text
peer uptime >= 99% preferred
usable_metric_range_uptime_percent >= 90%
geometry_2d_uptime_percent >= 90%
```

`fresh_metric_range_uptime_percent` is intentionally reported separately. It may be lower than usable uptime because bounded holdover is now an explicit continuity mechanism.

Additional truth gates:

```text
profile_id = android-ble-lab-v1
RSSI@1m = -69.19
n = 3.62
validated = true
domain = 0.5–5.0 m
physical confidence <= COARSE
no silent clamp
invalid RSSI excluded from valid queue
holdover <=10 s
sigma ages upward
expired range excluded
OUT_OF_DOMAIN excluded
reciprocal REJECT excluded
manual_geometry_override = false
human scanning = blocked
```

The dev-6 physical precision regression remains the protection against stabilizing continuity by weakening physical validity:

```text
MAE <= 2.0 m
max error <= 3.0 m
```

There is no need to re-run the full multi-distance calibration to prove that regression; it is a frozen CI fixture.

---

## 17. Evidence bundle to return

Create one folder:

```text
experimental7-continuity/
├── pixel10_continuity.txt
├── pixel7_continuity.txt
├── lenovo_continuity.txt
├── notes.txt                  # optional
└── screenshots/
    ├── pixel10_radar.png
    ├── pixel10_measurement_health.png
    ├── pixel10_validation_run.png
    ├── pixel10_ble_diagnostics.png
    ├── pixel10_reciprocal_fusion.png
    ├── pixel7_radar.png
    ├── pixel7_measurement_health.png
    ├── pixel7_validation_run.png
    ├── pixel7_ble_diagnostics.png
    ├── pixel7_reciprocal_fusion.png
    ├── lenovo_radar.png
    ├── lenovo_measurement_health.png
    ├── lenovo_validation_run.png
    ├── lenovo_ble_diagnostics.png
    └── lenovo_reciprocal_fusion.png
```

Compress it:

```bash
zip -r experimental7-continuity.zip experimental7-continuity/
```

Return that ZIP for analysis.

---

## 18. What will be calculated from the evidence

The review will calculate/verify:

- run duration;
- peer uptime;
- fresh metric uptime;
- usable metric uptime including bounded holdover;
- holdover share;
- 2D geometry uptime;
- invalid RSSI frequency;
- whether invalid values ever leaked into valid statistics;
- maximum observed holdover age;
- sigma aging behavior;
- scanner restart rate and cause;
- per-peer scan gaps;
- reciprocal disagreement/rejection;
- whether any expired/out-of-domain/rejected edge reached geometry;
- final human-test authorization decision.

---

## 19. Human test gate

Do not begin empty-scene / human LOS / motion / wall tests until this continuity result has been reviewed and explicitly accepted.

Passing experimental.7 validates only continuity of the already calibrated experimental sensor geometry in the tested environment. It does not validate human localization or rescue use.
