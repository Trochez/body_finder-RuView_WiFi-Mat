# Body Finder – RuView experimental.6: Android BLE metric geometry retest

## Purpose

This is the first physical test after promoting the multi-distance P0c profile to a validated **COARSE** metric source.

The goal is **not** human detection yet. The goal is to verify that Pixel 10 Pro, Pixel 7 Pro and Lenovo TB-J606L produce three defensible pairwise metric edges and that automatic 2D sensor geometry is physically reasonable.

The release remains experimental and is **not validated for rescue use**.

---

## 1. Use exactly one release

Download all files from the same newest `dev-*` prerelease whose `release-manifest.json` says:

```text
version = 0.2.0-experimental.6
ble_metric_profile = android-ble-lab-v1
ble_metric_profile_validated = true
ble_metric_profile_physical_confidence = COARSE
ble_metric_valid_distance_min_m = 0.5
ble_metric_valid_distance_max_m = 5.0
```

Do not mix APKs from another release.

Verify `SHA256SUMS` before installation.

---

## 2. Required Android devices

Recommended validated lab set:

- Pixel 10 Pro
- Pixel 7 Pro
- Lenovo TB-J606L

All three:

```text
Wi-Fi ON and connected to the same LAN
Bluetooth ON
Body Finder in foreground for the primary run
Battery saver OFF for the primary run
```

Lenovo / Android <=11:

```text
Location service ON
```

Do not enter X/Y/Z or any measured distance into Body Finder.

---

## 3. Install

```bash
adb devices -l
adb -s PIXEL10_SERIAL install -r body-finder-ruview-universal.apk
adb -s PIXEL7_SERIAL install -r body-finder-ruview-universal.apk
adb -s LENOVO_SERIAL install -r body-finder-ruview-universal.apk
```

Use `body-finder-ruview-legacy-minsdk21.apk` only if the universal APK cannot run on an older Android device. The physical metric validation in this document targets the universal APK.

---

## 4. Pre-flight check in Expert

On every phone verify:

```text
Build: 0.2.0-experimental.6
protocol: 2
Node geometry: AUTO ONLY
manual override: disabled
```

BLE calibration must show the equivalent of:

```text
profile_id: android-ble-lab-v1
validated: true
physical_confidence: COARSE
RSSI@1m: -69.19 dBm
path-loss n: 3.62
valid domain: 0.5–5.0 m
```

Lifecycle should show:

```text
foreground_service_state = RUNNING
last_error = null
wake_lock_held = true
wifi_lock_held = true
multicast_lock_held = true
```

If a device says Bluetooth disabled, permission required, foreground service failed, or multicast lock false with an error, stop and export its JSON before proceeding.

---

## 5. Physical layout

Create a non-collinear triangle. Keep every true pair distance inside the validated BLE domain.

Recommended example:

```text
Pixel 10 Pro -------- 3.0 m -------- Pixel 7 Pro
      \                              /
       \                            /
      ~2.5 m                    ~2.0 m
         \                        /
              Lenovo TB-J606L
```

The exact distances do not have to match the example. Requirements:

```text
each physical pair >= 0.5 m
each physical pair <= 5.0 m
triangle clearly non-collinear
phones approximately same height
phones stationary
portrait orientation preferred
not held in the hand
```

Measure final ground truth **after** the app has produced/exported its geometry, so the measurements cannot influence operation.

---

## 6. Start the validation run

1. Open Body Finder on all three devices.
2. Wait about 20 seconds for BLE/fabric stabilization.
3. In Expert tap **Start validation run** on all three.
4. Leave all devices untouched for **90 seconds**.
5. Do not calibrate the empty human scene yet.
6. Do not start human scanning yet.

During the run, the expected progression is:

```text
3 nodes
2 BLE peers per device
fresh BLE samples
VALID_METRIC observations inside 0.5–5.0 m
reciprocal fusion when both directions are present
3 unique metric pair edges
GEOMETRY_2D
3/3 nodes positioned
physical confidence = COARSE
```

A temporary 1D/insufficient state while samples acquire is acceptable. The final stable state is what matters.

---

## 7. What must NOT happen

Any of the following is a failure or a condition requiring review:

```text
30 m / 30 m / 30 m artificial triangle
silent clamp to 0.5 m or 5.0 m
HIGH physical confidence from BLE-only geometry
RSSI 127 participating in a median or calibration snapshot
OUT_OF_DOMAIN sample entering metric geometry
validated=false sample entering metric geometry
reciprocal state REJECT entering the solver
manual coordinate prompt
```

If an estimate is outside the profile domain, the correct behavior is:

```text
range_status = OUT_OF_DOMAIN_LOW or OUT_OF_DOMAIN_HIGH
distance_m = null
metric_valid = false
```

That may temporarily prevent 2D geometry. Do not move the domain boundary or type ground truth into the app to force a pass.

---

## 8. End and export

After 90 seconds:

1. Tap **End validation run** on each device.
2. Open Radar and take one screenshot per device.
3. Open Expert and capture:
   - Measurement health
   - Reciprocal fusion
   - Validation run
   - BLE/ranging diagnostics
   - Geometry solution / graph diagnostics
4. Tap **Share complete test JSON** on each device.

Recommended names:

```text
pixel10_metric3node.json
pixel7_metric3node.json
lenovo_metric3node.json

pixel10_radar.png
pixel7_radar.png
lenovo_radar.png

pixel10_expert.png
pixel7_expert.png
lenovo_expert.png
```

---

## 9. Measure external ground truth after export

Without moving the devices, measure with a tape:

```text
Pixel10 ↔ Pixel7 = ____ m
Pixel10 ↔ Lenovo = ____ m
Pixel7  ↔ Lenovo = ____ m
```

A simple `measurements.txt` is enough:

```text
pixel10_pixel7=3.07
pixel10_lenovo=2.46
pixel7_lenovo=2.13
units=m
method=tape
ground_truth_entered_into_app=NO
```

No separate ground-truth JSON is required.

---

## 10. Evidence required for acceptance

Send one ZIP with:

```text
experimental6-metric-geometry/
├── pixel10_metric3node.json
├── pixel7_metric3node.json
├── lenovo_metric3node.json
├── measurements.txt
└── screenshots/
    ├── pixel10_radar.png
    ├── pixel10_expert.png
    ├── pixel7_radar.png
    ├── pixel7_expert.png
    ├── lenovo_radar.png
    └── lenovo_expert.png
```

The analysis will calculate:

- three estimated pairwise distances;
- absolute error per pair;
- pairwise MAE;
- pairwise max error;
- reciprocal disagreement;
- source/fusion mode;
- metric-range uptime;
- geometry 2D uptime;
- aligned node-position geometry error where appropriate;
- whether reported uncertainty remains conservative.

---

## 11. Acceptance gates

Primary metric gate:

```text
3 active nodes
3 unique metric pairs
GEOMETRY_2D
3/3 positions
physical_confidence <= COARSE
pairwise MAE <= 2.0 m
maximum pair error <= 3.0 m
```

Truth gates:

```text
profile_id = android-ble-lab-v1
validated = true
no silent clamp
no invalid RSSI 127 used
out-of-domain -> non-metric
reciprocal REJECT -> excluded
manual_geometry_override = false
```

If the three metric edges are not simultaneously available because a raw BLE estimate exits the calibrated 0.5–5.0 m model domain, report that outcome; it is a valid negative result and must not be forced.

---

## 12. Optional stability run after the primary gate

Only after the 90-second geometry test succeeds:

1. Start a fresh validation run on all three.
2. Keep screens awake and apps in foreground.
3. Run 5 minutes.
4. End/export all three JSONs.

Targets:

```text
peer_expire_delta = 0 ideal
all_peer_uptime_percent >= 90%
metric_range_uptime_percent >= 90%
geometry_2d_uptime_percent >= 90%
```

A screen-off run may be performed separately using `ANDROID_POWER_LIFECYCLE_RETEST.md`.

---

## 13. Human-presence gate

Do **not** begin empty-scene, LOS person, moving person or wall tests until the three-node metric geometry result above has been reviewed and explicitly accepted.

Passing this test validates only experimental sensor geometry for the tested environment. It does not validate human localization or rescue use.
