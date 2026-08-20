# Body Finder experimental.5 — Android BLE calibration and range-precision retest

This is the **first physical test to run** on `0.2.0-experimental.5`.

## Important expected behavior

Experimental.5 intentionally does **not** treat commodity Android BLE RSSI as a metric distance yet. T2/T4b from experimental.4 proved the BLE plumbing, but the observed RSSI values did not support a defensible single-layout metric calibration. Therefore the bundled profile `android-ble-screening-v1` has:

```text
validated = false
metric_valid = false for BLE_RSSI
range_status = PROXIMITY_ONLY (when enough fresh samples exist)
distance_m = null
raw_distance_m = diagnostic only
```

This is not a regression. It prevents the previous false 30 m triangle.

A true Android system-range result (UWB/BLE CS/NAN RTT/BLE RSSI via RangingManager when it actually returns a distance) may still be metric and can enter the geometry solver with its real provenance.

## Devices

Required:

- Pixel 10 Pro;
- Pixel 7 Pro;
- Lenovo TB-J606L;
- one tape measure or laser meter;
- same Wi-Fi LAN;
- Bluetooth enabled;
- Location enabled on Lenovo/API30.

Use all APKs from **one and the same `dev-*` release**.

## Install

```bash
adb devices -l
adb -s PIXEL10_SERIAL install -r body-finder-ruview-universal.apk
adb -s PIXEL7_SERIAL  install -r body-finder-ruview-universal.apk
adb -s LENOVO_SERIAL  install -r body-finder-ruview-universal.apk
```

Use `body-finder-ruview-legacy-minsdk21.apk` on Lenovo only if the universal APK genuinely cannot install/run. The calibration dataset should preferably be collected with the universal APK on all three devices.

Verify on every device in **Expert**:

```text
Build: 0.2.0-experimental.5
protocol 2
Node geometry: AUTO ONLY
manual override disabled
BLE scan: active after peers are present
calibration profile: android-ble-screening-v1
validated: false
```

## Test P0 — prove the old 30 m bug is gone

Place the three phones roughly in the same triangular layout used previously.

Do not enter any physical distance into the app.

Wait 60 seconds.

Expected:

```text
3 nodes
2 BLE peers per node, when radio reception allows
BLE evidence/proximity present
BLE_RSSI range_status = PROXIMITY_ONLY
BLE_RSSI distance_m = null
raw_distance_m may be present
metric edge count = 0 unless a true system metric range is produced
```

The application must **not** recreate the old `30 m / 30 m / 30 m` geometry from the unvalidated BLE profile.

Take one Radar and one Expert screenshot per Android.

## Multi-distance calibration dataset

The objective is to determine empirically whether BLE RSSI can provide sufficiently reproducible metric scale for this device mix.

### Distances

Collect at:

```text
0.5 m
1.0 m
2.0 m
3.0 m
5.0 m
8.0 m optional if the room permits
```

### Pair combinations

Repeat each distance for:

```text
Pixel10 ↔ Pixel7
Pixel10 ↔ Lenovo
Pixel7  ↔ Lenovo
```

Both devices must remain running because each direction is independently observed.

### Placement

For each measurement:

1. Put the two target phones at the requested tape-measured distance.
2. Keep them approximately at the same height.
3. Keep the third phone at least several meters away or close its Body Finder app for this pair-specific collection.
4. Do not hold either phone in your hand during the sampling interval.
5. Keep normal portrait orientation for the first dataset.
6. Ensure screens remain on for the primary dataset.
7. Wait 20 seconds after moving the devices before starting the measurement run.

### Collect one validation run per distance

On **both participating phones**:

1. Open **Expert**.
2. Tap **Start validation run / Iniciar corrida de validación**.
3. Wait **60 seconds** without moving the phones.
4. Tap **End validation run**.
5. Tap **Share complete test JSON**.

The exported report contains a `calibration_snapshot` with rolling raw RSSI samples and a diagnostic raw estimate. Ground truth is deliberately absent from runtime.

### File naming

Use exactly this convention where practical:

```text
calibration/
  pixel10-pixel7/
    0p5m-pixel10.json
    0p5m-pixel7.json
    1p0m-pixel10.json
    1p0m-pixel7.json
    2p0m-pixel10.json
    2p0m-pixel7.json
    3p0m-pixel10.json
    3p0m-pixel7.json
    5p0m-pixel10.json
    5p0m-pixel7.json

  pixel10-lenovo/
    ...

  pixel7-lenovo/
    ...
```

Also create:

```text
calibration/ground-truth.json
```

Example:

```json
{
  "measurement_method": "tape",
  "units": "m",
  "environment": "indoor open room",
  "heights_m": {
    "pixel10": 0.75,
    "pixel7": 0.75,
    "lenovo": 0.75
  },
  "requested_distances_m": [0.5, 1.0, 2.0, 3.0, 5.0],
  "notes": "Phones stationary; normal portrait orientation; no ground truth entered into Body Finder."
}
```

Do **not** add measured coordinates to the application.

## Optional orientation sensitivity subset

After completing the main dataset, repeat only `1 m` and `3 m` for each pair with one phone rotated 180 degrees. Name them, for example:

```text
3p0m-rot180-pixel10.json
3p0m-rot180-pixel7.json
```

This allows us to estimate antenna/orientation sensitivity.

## What I need returned

Minimum calibration evidence:

```text
15 physical pair-distance configurations
= 3 pairs × 5 distances
= 30 Android JSON exports if both endpoints export each configuration

calibration/ground-truth.json
at least one Expert screenshot per device at 1 m and 5 m
notes.txt describing room, approximate height and any unusual event
```

Zip it:

```bash
zip -r body-finder-exp5-calibration.zip calibration/
```

## Acceptance analysis

The included validation tool fits a log-distance profile only from external labelled data and refuses non-physical fits.

Expected analysis gates before BLE RSSI can be marked metric:

```text
required distances present: 0.5, 1, 2, 3, 5 m
fitted path-loss exponent > 0.5 and <= 8
leave-one-distance-out MAE <= 2.0 m
leave-one-distance-out max error <= 3.0 m
silent saturation rate = 0%
```

If BLE RSSI fails those gates, it remains `PROXIMITY_ONLY`. That is the correct outcome; the software must not invent a metric distance.

## Three-node precision retest after a profile is accepted

Only after a new validated profile is generated and shipped in a subsequent build:

1. Arrange Pixel10, Pixel7 and Lenovo in a non-collinear triangle.
2. Start a fresh validation run on all three.
3. Wait 90 seconds.
4. End/export all three reports.
5. Measure the three pairwise ground-truth distances **after** the app has solved.
6. Return the three reports, screenshots and ground truth.

Target initial gate:

```text
pairwise MAE <= 2.0 m
max pair error <= 3.0 m
3 metric pairs
3/3 nodes solved
physical confidence no higher than evidence warrants
```

Human-presence tests remain blocked until metric sensor geometry passes this gate.
