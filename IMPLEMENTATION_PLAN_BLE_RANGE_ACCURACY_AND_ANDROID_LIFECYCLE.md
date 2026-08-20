# Body Finder – RuView — BLE Range Accuracy & Android Lifecycle Implementation Plan

> Target: `0.2.0-experimental.5` / protocol v2  
> Basis: physical T2/T4/T4b on Pixel 10 Pro, Pixel 7 Pro and Lenovo TB-J606L  
> Status: implemented through the software/release portion; physical calibration/acceptance requires the new device run described in release docs.

## 1. Physical findings that drive this increment

Experimental.4 closed discovery/ranging plumbing but produced a physically false metric result:

```text
external ground truth:
Lenovo ↔ Pixel7  ~1.18 m
Pixel10 ↔ Pixel7 ~3.20 m
Lenovo ↔ Pixel10 ~3.50 m

experimental.4 BLE_RSSI:
30.0 m
30.0 m
30.0 m
```

Code audit confirmed the root cause: Android advertised `txPowerLevel` metadata was being used as if it were RSSI at 1 metre in the log-distance equation, followed by a silent clamp at 30 m.

T4b also demonstrated that when all devices were awake the three-node BLE/UDP fabric could finish with two active peers/device and three graph pairs. Therefore screen-off/background behavior is treated as a lifecycle/power-management problem to characterize and harden, not as proof of a fundamentally broken fabric.

## 2. Non-negotiable rules

- no manual X/Y/Z in normal operation;
- ground truth never enters the runtime solver;
- no silent distance clamp;
- advertised TxPower is not RSSI@1m;
- unvalidated BLE RSSI is proximity evidence only;
- only valid numeric metric observations constrain geometry;
- graph condition/residual are not labels of physical accuracy;
- Android system ranging failure never disables independent BLE evidence;
- human/LOS/wall tests remain blocked until metric sensor geometry passes physical gates;
- no rescue claims.

## 3. Team and roles

| Role | Responsibility |
|---|---|
| TL — Tech Lead / Solution Architect | architecture, truth policy, priorities, final acceptance |
| RCE — RF Calibration / Ranging Engineer | RF semantics, estimator, profile, uncertainty, reciprocal fusion |
| ARF — Android RF/BLE Engineer | scan/advertise, samples, bindings, rebinds, RangingManager integration |
| APL — Android Power/Lifecycle Engineer | foreground service, wake/Wi-Fi/multicast locks, recovery |
| PGE — Protocol/Geometry Engineer | range contract, metric-edge gating, solver truth and covariance |
| MUI — Mobile UX Engineer | Expert truth UI, validation-run controls, export |
| QAE — QA/Automation Engineer | fixtures, contract tests, CI regression gates |
| VDE — Validation/Data Engineer | calibration fit, MAE/RMSE/holdout/coverage reports |
| FTL — Field Test Lead | physical placements, controlled device runs, ground truth |
| DRE — DevOps/Release Engineer | CI, packaging, checksums, SBOM, prerelease |

## 4. RACI

| Workstream | Accountable | Responsible | Consulted |
|---|---|---|---|
| RF semantics/profile | TL | RCE | ARF,VDE |
| Android BLE integration | TL | ARF | RCE,QAE |
| Lifecycle/power | TL | APL | ARF,QAE |
| Metric graph | TL | PGE | RCE,QAE |
| UI/export | TL | MUI | PGE,VDE |
| Calibration analysis | TL | VDE | RCE,FTL |
| Physical acceptance | TL | FTL | VDE,QAE |
| CI/release | TL | DRE | QAE |

## 5. Implemented architecture

### 5.1 RF semantic separation

Native code uses distinct types for:

```text
RssiDbm
TransmitPowerDbm
RssiAtOneMeterDbm
PathLossExponent
DistanceMeters
```

This prevents the exact experimental.4 semantic error from being reintroduced accidentally.

### 5.2 Versioned BLE calibration profile

`BleRangeCalibrationProfile` contains:

```text
profile id/source
RSSI@1m prior + sigma
path-loss exponent + sigma
valid model domain
sample count/environment
validated flag
validation note
```

The bundled `android-ble-screening-v1` is deliberately `validated=false` because T2/T4b alone are not enough to support a reproducible metric relationship.

### 5.3 Truth-preserving range status

Possible states:

```text
VALID
PROXIMITY_ONLY
UNCALIBRATED
SATURATED_LOW
SATURATED_HIGH
INSUFFICIENT_SAMPLES
STALE
NONFINITE
OUT_OF_MODEL_DOMAIN
```

Unvalidated BLE evidence exports a diagnostic `raw_distance_m` but:

```text
metric_valid=false
distance_m=null
```

so the metric solver cannot consume it.

### 5.4 No silent clamp

A raw estimate outside the model domain is labelled saturated and withheld rather than coerced into a boundary value.

### 5.5 Geometry truth

The diagnostic layer separates:

```text
RF evidence pairs
metric edge pairs
proximity-only samples
saturated samples
uncalibrated samples
measurement health
physical confidence
```

The UI labels `condition` as **graph condition** and explicitly warns when RF topology exists but no metric geometry exists.

### 5.6 Android field session

Experimental.5 adds a connected-device foreground service with:

- persistent notification;
- partial CPU wake lock;
- high-performance Wi-Fi lock;
- multicast lock;
- BLE scan stall watchdog/restart;
- service/power/screen diagnostics.

### 5.7 Validation-run model

The app exposes Start/End Validation Run and records per-run deltas instead of relying on process-lifetime counters:

```text
run id / elapsed
peer expiration delta
address rebind delta
scan restart delta
tx/rx packet delta
all-peer uptime
BLE evidence uptime
metric-range uptime
2D geometry uptime
```

### 5.8 Rebind characterization

Rebind events include only hashed address fingerprints:

```text
identity
previous fingerprint
new fingerprint
timestamp
reason
```

Duplicate changes are debounced. Raw MAC addresses are never exported.

### 5.9 Android API36+ system ranging

RangingManager now uses bounded exponential retry and a circuit breaker. Fresh real system distance remains preferred. Failure does not clear BLE evidence.

## 6. Atomic backlog and ownership

### Epic A — evidence lock

- **QAE A-01** freeze experimental.4 T2/T4b saturation fixture — DONE.
- **VDE A-02** preserve ground truth as validation-only data — DONE in test protocol; never runtime input.
- **QAE A-03** reproduce old saturation cause in automated contract — DONE.

### Epic B — estimator audit/fix

- **RCE B-01** locate old `TxPower-RSSI` path-loss equation — DONE.
- **RCE B-02** locate 30 m clamp — DONE.
- **ARF B-03** trace Android `ScanRecord.txPowerLevel` — DONE.
- **RCE B-04** separate TxPower from RSSI@1m — DONE.
- **RCE B-05** remove silent clamp — DONE.
- **QAE B-06** CI regression forbids old formula/clamp — DONE.

### Epic C — calibration profile/range statuses

- **RCE C-01** implement profile contract — DONE.
- **RCE C-02** implement range status enum — DONE.
- **RCE C-03** export raw estimate/provenance — DONE.
- **RCE C-04** withhold metric distance for unvalidated profile — DONE.
- **DRE C-05** ship profile/schema as artifacts — DONE in release workflow.
- **VDE C-06** collect multi-distance dataset — PHYSICAL STEP REQUIRED.
- **VDE C-07** fit profile and holdout metrics — TOOL IMPLEMENTED; awaits dataset.

### Epic D — graph/geometry truth

- **PGE D-01** distinguish evidence vs metric pairs — DONE.
- **PGE D-02** exclude null/non-metric BLE range from metric geometry — DONE by range contract and graph gate.
- **MUI D-03** show measurement health/physical confidence — DONE.
- **MUI D-04** rename condition to graph condition — DONE.
- **QAE D-05** no false 30m geometry contract — DONE.

### Epic E — lifecycle

- **APL E-01** foreground connected-device service — DONE.
- **APL E-02** persistent notification — DONE.
- **APL E-03** CPU/Wi-Fi/multicast locks — DONE.
- **ARF E-04** BLE callback-stall watchdog — DONE.
- **APL E-05** lifecycle diagnostics — DONE.
- **FTL E-06** screen-on 5min physical test — REQUIRED.
- **FTL E-07** screen-off 5min physical test — REQUIRED.

### Epic F — validation-run telemetry

- **MUI F-01** Start/End run controls — DONE.
- **ARF F-02** baseline counters — DONE.
- **VDE F-03** per-run uptime summaries — DONE.
- **MUI F-04** export run — DONE.

### Epic G — address rebinds

- **ARF G-01** timestamp/fingerprint/reason — DONE.
- **ARF G-02** debounce duplicate changes — DONE.
- **VDE G-03** characterize physical rebind rate — awaits lifecycle test data.

### Epic H — RangingManager

- **ARF H-01** failure counters — DONE.
- **ARF H-02** bounded exponential backoff — DONE.
- **ARF H-03** circuit breaker — DONE.
- **QAE H-04** fallback independence preserved — enforced by contract/review.

### Epic I — calibration tooling

- **VDE I-01** pure-Python fitter — DONE.
- **VDE I-02** nonphysical exponent rejection — DONE.
- **VDE I-03** leave-one-distance-out evaluation — DONE.
- **VDE I-04** MAE/RMSE/max-error gate — DONE.
- **DRE I-05** ship tooling in validation ZIP — DONE in release workflow.

### Epic J — release

- **DRE J-01** Android universal APK/AAB — release workflow.
- **DRE J-02** legacy APK — release workflow.
- **DRE J-03** Linux tar/deb — release workflow.
- **DRE J-04** Windows zip — release workflow.
- **DRE J-05** iOS Simulator zip — release workflow.
- **DRE J-06** docs/profile/schema/fixtures/tools — release workflow.
- **DRE J-07** checksums/SBOM/manifest — release workflow.
- **TL J-08** prerelease truth notes — release workflow.

## 7. Physical calibration dataset required

Distances:

```text
0.5, 1, 2, 3, 5 m
8 m optional
```

Pairs:

```text
Pixel10 ↔ Pixel7
Pixel10 ↔ Lenovo
Pixel7 ↔ Lenovo
```

Both endpoint exports are required for each pair/distance because receiver bias matters.

The detailed procedure is `ANDROID_RANGE_PRECISION_RETEST.md`.

## 8. Metric acceptance gate

BLE RSSI may be promoted from `PROXIMITY_ONLY` only if the multi-distance holdout validates:

```text
path-loss exponent > 0.5 and <= 8
required distance coverage complete
leave-one-distance-out MAE <= 2.0 m
max error <= 3.0 m
silent saturation rate = 0
```

If these gates fail, BLE remains proximity-only and precise metric geometry requires a better ranging source.

## 9. Lifecycle acceptance

Awake 5-minute target:

```text
peer expiry delta = 0 ideal
all-peer uptime >= 90%
BLE evidence uptime >= 90%
```

Screen-off minimum:

- foreground service truthfully remains running or reports failure;
- app automatically reacquires after unlock;
- no stale/fake metric distance is generated;
- reacquisition <= 30 s target.

Detailed procedure: `ANDROID_POWER_LIFECYCLE_RETEST.md`.

## 10. Release artifacts

The prerelease must contain:

```text
body-finder-ruview-universal.apk
body-finder-ruview.aab
body-finder-ruview-legacy-minsdk21.apk
body-finder-node-linux-x86_64.tar.gz
body-finder-node-linux-x86_64.deb
body-finder-node-windows-x86_64.zip
body-finder-ruview-ios-simulator.zip
IMPLEMENTATION_PLAN_BLE_RANGE_ACCURACY_AND_ANDROID_LIFECYCLE.md
ANDROID_RANGE_PRECISION_RETEST.md
ANDROID_POWER_LIFECYCLE_RETEST.md
TESTING_AUTOGEOMETRY_RELEASE.md
ble-range-calibration-profiles.json
ble-range-calibration-schema.json
body-finder-validation-tools.zip
ble-range-screening-fixtures.zip
release-manifest.json
capability-matrix.json
protocol-version.txt
ruview-upstream-lock.json
model-manifest.json
SHA256SUMS
SBOM.spdx.json
```

## 11. Definition of Done

Software/release DONE requires:

- no old TxPower/RSSI@1m formula;
- no silent clamp;
- profile versioned and unvalidated until physical gate;
- unvalidated BLE evidence cannot form metric geometry;
- validation-run telemetry works;
- Android foreground session works;
- rebind diagnostics work;
- bounded API36 retry works;
- CI green;
- prerelease artifacts published.

Physical DONE requires the user/device-lab dataset. Until then:

```text
human_localization_validated = false
through_wall_validated = false
rescue_use_validated = false
```

## 12. Final product decision rule

The calibration experiment is allowed to conclude that BLE RSSI is not good enough for metric geometry. In that case the correct architecture is:

```text
BLE RSSI → proximity/topology evidence
UWB / BLE CS / RTT / other verified source → metric scale when actually available
```

A truthful absence of metric geometry is preferable to a visually convincing false geometry.
