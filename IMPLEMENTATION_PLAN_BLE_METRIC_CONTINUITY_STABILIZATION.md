# Body Finder – RuView
# Implementation Plan — BLE Metric Continuity Stabilization

> Baseline: `dev-6` / `0.2.0-experimental.6`  
> Target: `0.2.0-experimental.7`  
> Protocol: v2  
> Status: implementation source of truth

## 1. Goal

`dev-6` passed physical metric accuracy with the frozen profile:

```text
android-ble-lab-v1
RSSI@1m = -69.19 dBm
n = 3.62
validated = true
valid domain = 0.5–5.0 m
physical_confidence = COARSE
```

The primary geometry test produced pairwise MAE ~0.322 m and maximum error ~0.496 m, but BLE metric continuity was much lower than required on Pixel 10/Pixel 7 and 2D geometry uptime was only ~58–60%. Peer/network/lifecycle uptime remained high. Therefore this increment must improve temporal availability without changing the calibrated physics.

## 2. Non-negotiable constraints

1. Do not change RSSI@1m, path-loss exponent, valid domain or COARSE confidence.
2. Do not reintroduce silent clamping.
3. RSSI `127` or other invalid RSSI values must never enter the valid RF queue, median, estimator or calibration samples.
4. A previous valid distance may be retained only through an explicit bounded `HOLDOVER` state.
5. HOLDOVER retains the original measurement/provenance; it does not fabricate a new measurement.
6. HOLDOVER sigma increases with age.
7. Hard expiry removes the edge.
8. New `OUT_OF_DOMAIN`, invalidating evidence, peer expiry/session change or reciprocal `REJECT` must not be hidden by an old cached edge.
9. BLE-only physical confidence cannot exceed COARSE.
10. Human localization and rescue validation remain false until a subsequent explicit gate.

## 3. Team size

Recommended logical team: **7 members**.

- **TL — Tech Lead / Solution Architect:** architecture, thresholds, gates, merge/release approval.
- **ABR — Android BLE Runtime Engineer:** scan callbacks, RSSI queues, cache, watchdog/recovery.
- **RRE — RF/Ranging Reliability Engineer:** freshness, holdover, sigma aging, expiry semantics.
- **PGE — Protocol & Geometry Engineer:** temporal provenance, fusion, graph/solver gating.
- **MUI — Mobile UX/Diagnostics Engineer:** Radar/Expert, counters, export/run finalization.
- **QAE — QA/Automation Engineer:** timeline/sentinel/regression tests.
- **DVE — DevOps & Field Validation Engineer:** CI, release assets, physical 5-minute retest.

Minimum viable team: 4 people combining TL+PGE, ABR+RRE, MUI+QAE, DVE. Maximum recommended: 8.

## 4. RACI

| Area | Accountable | Responsible | Consulted |
|---|---|---|---|
| RSSI sanitation | TL | ABR | QAE, RRE |
| Freshness/holdover | TL | RRE | ABR, PGE |
| Scanner watchdog | TL | ABR | QAE |
| Graph temporal gating | TL | PGE | RRE |
| UI/export | TL | MUI | QAE, PGE |
| Regression tests | QAE | QAE | ABR, PGE |
| Release | TL | DVE | QAE |
| Physical retest | TL | DVE | RRE, QAE |

## 5. Temporal architecture

### 5.1 States

```text
ACQUIRING
FRESH
HOLDOVER
STALE
EXPIRED
OUT_OF_DOMAIN
INVALID
```

`FRESH` means a current validated metric estimate exists. `HOLDOVER` means current samples are temporarily insufficient but a last-valid in-domain metric estimate is still inside a bounded temporal window. `EXPIRED` cannot enter metric geometry.

### 5.2 Initial policy

```text
valid RSSI sample window = 5 s
minimum valid samples = 3
fresh estimate window = 5 s
holdover maximum = 10 s
hard expiry = >10 s
sigma aging = 0.15 m/s
holdover sigma cap = 5 m
```

All values are versioned constants and CI-protected.

### 5.3 Last-valid state

Persist per peer:

```text
peer_node_id
ble_identity
distance_m
sigma_m
raw_distance_m
median_valid_rssi_dbm
profile_id
calibration_state
original observation monotonic timestamp
last-valid wall timestamp
source provenance
```

### 5.4 Invalidating evidence

Immediately cancel cached holdover when any of these is known:

```text
new OUT_OF_DOMAIN metric-model result
new non-finite/explicit invalid metric result
peer expiry
session/identity reset
Bluetooth/fabric reset
reciprocal REJECT at graph/fusion stage
```

A short absence of valid samples or one invalid Android sentinel must not itself fabricate or destroy physics; it only changes temporal state.

## 6. RSSI queue architecture

Before:

```text
ScanResult -> raw queue -> filter later
```

Target:

```text
ScanResult
  -> validate RSSI
       -> valid: valid RSSI queue
       -> invalid: diagnostic-only invalid event ring/counter
```

Per peer expose:

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
```

The calibration snapshot contains only valid RSSI samples.

## 7. Scan-gap semantics

Track independently:

```text
last raw scanner callback
last valid Body Finder RSSI callback
last valid RSSI callback per peer
```

Classify global scanner health separately from a single-peer gap. Scanner restart is allowed only for global callback silence; a single peer becoming temporarily quiet cannot trigger scanner restart thrashing.

## 8. Graph/fusion semantics

The solver can consume only:

```text
FRESH
HOLDOVER (bounded, with aged sigma)
```

It cannot consume:

```text
STALE
EXPIRED
OUT_OF_DOMAIN
INVALID
reciprocal REJECT
```

Reciprocal fusion retains source temporal states. If any source is HOLDOVER, the fused edge is explicitly marked HOLDOVER. Existing inverse-variance fusion/disagreement thresholds remain intact.

## 9. Temporal measurement health

Expose:

```text
fresh_metric_edge_count
holdover_metric_edge_count
oldest_metric_edge_age_ms
geometry_temporal_quality
```

Temporal quality:

```text
FRESH_ONLY
MIXED_FRESH_HOLDOVER
HOLDOVER_DOMINANT
NO_METRIC_GEOMETRY
```

This is distinct from physical confidence, which remains COARSE for validated BLE-only geometry.

## 10. Validation-run semantics

Track separately:

```text
all_peer_uptime_percent
ble_evidence_uptime_percent
fresh_metric_range_uptime_percent
usable_metric_range_uptime_percent
holdover_metric_uptime_percent
geometry_2d_uptime_percent
```

The export must contain a stable `snapshot_wall_ms`/`snapshot_elapsed_ms`. If Share is pressed while a run is still active, experimental.7 auto-finalizes the run before producing the exported JSON and reports that behavior.

## 11. Atomic backlog

### Epic A — Baseline protection

| ID | Owner | Pri | Atomic task | Acceptance |
|---|---|---|---|---|
| A-01 | QAE | P0 | Add dev-6 accuracy/continuity fixture | Fixture parseable |
| A-02 | TL | P0 | Freeze profile ID | CI fails on drift |
| A-03 | TL | P0 | Freeze -69.19 / 3.62 | CI fails on drift |
| A-04 | TL | P0 | Freeze 0.5–5m domain | CI fails on drift |
| A-05 | QAE | P0 | Preserve dev-6 MAE/max gates | MAE<=2,max<=3 |

### Epic B — RSSI sanitation

| ID | Owner | Pri | Atomic task | Acceptance |
|---|---|---|---|---|
| B-01 | ABR | P0 | Centralize RSSI validator | Single predicate |
| B-02 | ABR | P0 | Validate before queue insertion | 127 never enters valid queue |
| B-03 | ABR | P0 | Add invalid-event diagnostic ring | No estimator use |
| B-04 | ABR | P0 | Add total/per-peer invalid counters | Exported |
| B-05 | ABR | P0 | Store latest valid RSSI separately | Exported |
| B-06 | ABR | P0 | Store latest invalid RSSI separately | Exported |
| B-07 | ABR | P0 | Median uses valid queue only | Sentinel cannot distort median |
| B-08 | ABR | P0 | Calibration snapshot uses valid queue only | No 127 in samples |
| B-09 | QAE | P0 | Sentinel regression test | PASS |

### Epic C — Sample accounting

| ID | Owner | Pri | Atomic task | Acceptance |
|---|---|---|---|---|
| C-01 | ABR | P0 | Add raw count 5s | Exported |
| C-02 | ABR | P0 | Add valid count 5s | Exported |
| C-03 | ABR | P0 | Add invalid count 5s | Exported |
| C-04 | ABR | P1 | Add raw/valid/invalid 8s | Exported |
| C-05 | MUI | P0 | Readiness uses valid count | raw=3/valid=2 remains insufficient |
| C-06 | QAE | P0 | Counter timeline test | PASS |

### Epic D — Last-valid range cache

| ID | Owner | Pri | Atomic task | Acceptance |
|---|---|---|---|---|
| D-01 | ABR | P0 | Add LastValidRangeState | Compiles |
| D-02 | ABR | P0 | Cache only valid metric estimate | Test |
| D-03 | ABR | P0 | Preserve distance/sigma/raw | Test |
| D-04 | ABR | P0 | Preserve original timestamps | Exported |
| D-05 | ABR | P0 | Preserve profile provenance | Exported |
| D-06 | QAE | P0 | Invalid estimate cannot populate cache | PASS |

### Epic E — Temporal state machine

| ID | Owner | Pri | Atomic task | Acceptance |
|---|---|---|---|---|
| E-01 | RRE | P0 | Define FRESH | Spec/test |
| E-02 | RRE | P0 | Define HOLDOVER | Spec/test |
| E-03 | RRE | P0 | Define STALE/EXPIRED | Spec/test |
| E-04 | ABR | P0 | Implement state transitions | Deterministic |
| E-05 | QAE | P0 | Boundary tests 5s/10s | PASS |

### Epic F — Sigma aging

| ID | Owner | Pri | Atomic task | Acceptance |
|---|---|---|---|---|
| F-01 | RRE | P0 | Set aging rate 0.15m/s | Versioned |
| F-02 | RRE | P0 | Set conservative cap | Versioned |
| F-03 | ABR | P0 | Apply aging during HOLDOVER | Sigma monotonically grows |
| F-04 | QAE | P0 | Fresh vs holdover sigma test | Holdover >= fresh |

### Epic G — Holdover invalidation

| ID | Owner | Pri | Atomic task | Acceptance |
|---|---|---|---|---|
| G-01 | ABR | P0 | OUT_OF_DOMAIN clears cache | Test |
| G-02 | PGE | P0 | Reciprocal REJECT excluded | Test |
| G-03 | ABR | P0 | Peer expiry clears cache | Test |
| G-04 | ABR | P0 | Runtime reset clears cache | Test |
| G-05 | QAE | P0 | Invalidating-evidence suite | PASS |

### Epic H — Scanner gap handling

| ID | Owner | Pri | Atomic task | Acceptance |
|---|---|---|---|---|
| H-01 | ABR | P0 | Track scanner start/raw callback | Exported |
| H-02 | ABR | P0 | Add global scanner health state | Exported |
| H-03 | ABR | P0 | Add per-peer gap state | Exported |
| H-04 | ABR | P0 | Restart only on global stall | No single-peer thrash |
| H-05 | ABR | P0 | Keep restart cooldown | Bounded |
| H-06 | QAE | P0 | Global vs peer-gap tests | PASS |

### Epic I — Fusion/graph temporal gating

| ID | Owner | Pri | Atomic task | Acceptance |
|---|---|---|---|---|
| I-01 | PGE | P0 | FRESH edge accepted | PASS |
| I-02 | PGE | P0 | HOLDOVER edge accepted <=10s | PASS |
| I-03 | PGE | P0 | expired edge rejected | PASS |
| I-04 | PGE | P0 | Carry source temporal state in reciprocal fusion | Provenance |
| I-05 | PGE | P0 | Fresh+holdover fusion conservative | PASS |
| I-06 | PGE | P0 | REJECT never enters solver | PASS |
| I-07 | QAE | P0 | Temporal fusion matrix | PASS |

### Epic J — Measurement health/UI

| ID | Owner | Pri | Atomic task | Acceptance |
|---|---|---|---|---|
| J-01 | PGE | P0 | Add fresh edge count | Exported |
| J-02 | PGE | P0 | Add holdover edge count | Exported |
| J-03 | PGE | P0 | Add oldest edge age | Exported |
| J-04 | PGE | P0 | Add temporal quality | Exported |
| J-05 | MUI | P0 | Show HOLD badge | Radar |
| J-06 | MUI | P0 | Show valid/invalid RSSI diagnostics | Expert |
| J-07 | MUI | P0 | Never imply HOLDOVER is fresh | Truthful UI |

### Epic K — Validation/export

| ID | Owner | Pri | Atomic task | Acceptance |
|---|---|---|---|---|
| K-01 | ABR | P0 | Track fresh metric uptime | JSON |
| K-02 | ABR | P0 | Track usable metric uptime | JSON |
| K-03 | ABR | P0 | Track holdover share | JSON |
| K-04 | MUI | P1 | Add export snapshot timestamp | JSON |
| K-05 | MUI | P1 | Auto-end active run before Share | active=false export |
| K-06 | QAE | P1 | Export active/end tests | PASS |

### Epic L — CI/release

| ID | Owner | Pri | Atomic task | Acceptance |
|---|---|---|---|---|
| L-01 | QAE | P0 | Add continuity static contract | PASS |
| L-02 | DVE | P0 | Run contract in CI | Required job |
| L-03 | DVE | P0 | Android universal APK+AAB | Green |
| L-04 | DVE | P0 | Android legacy regression | Green |
| L-05 | DVE | P1 | Linux/Windows regression | Green |
| L-06 | DVE | P1 | iOS Simulator regression | Green |
| L-07 | DVE | P0 | Bump experimental.7 / report v9 | Manifest |
| L-08 | DVE | P0 | Add plan/retest/fixtures to release | Assets |
| L-09 | DVE | P0 | Generate SBOM/SHA256 | Verified |
| L-10 | TL | P0 | Verify human/rescue false | Release gate |

### Epic M — Physical acceptance

| ID | Owner | Pri | Atomic task | Acceptance |
|---|---|---|---|---|
| M-01 | DVE | P0 | Install one dev-* on 3 Androids | Same build |
| M-02 | DVE | P0 | Non-collinear 0.5–5m layout | Valid domain |
| M-03 | DVE | P0 | 30s stabilization | 3 nodes |
| M-04 | DVE | P0 | Fresh 5-minute validation run | Complete |
| M-05 | DVE | P0 | End and export 3 JSONs | Evidence |
| M-06 | RRE | P0 | Analyze fresh metric uptime | Report |
| M-07 | RRE | P0 | Analyze usable metric uptime | >=90% target |
| M-08 | RRE | P0 | Analyze 2D uptime | >=90% target |
| M-09 | RRE | P0 | Analyze holdover ages/sigma | Bounded/truthful |
| M-10 | TL | P0 | Authorize/block human tests | Explicit decision |

## 12. CI gates

```text
profile values unchanged
valid domain unchanged
no silent clamp
invalid RSSI rejected prequeue
calibration snapshot contains valid RSSI only
holdover <=10s
holdover sigma grows with age
expired/out-of-domain/rejected evidence excluded
single-peer gap cannot trigger global restart
report version = 9
Android versionCode = 7
human scanning disabled
all target builds green
```

## 13. Release artifacts

Mandatory release artifacts include:

```text
body-finder-ruview-universal.apk
body-finder-ruview.aab
body-finder-ruview-legacy-minsdk21.apk
body-finder-node-linux-x86_64.tar.gz
body-finder-node-linux-x86_64.deb
body-finder-node-windows-x86_64.zip
body-finder-ruview-ios-simulator.zip
IMPLEMENTATION_PLAN_BLE_METRIC_CONTINUITY_STABILIZATION.md
ANDROID_BLE_METRIC_CONTINUITY_RETEST.md
ble-range-calibration-profiles.json
ble-range-calibration-schema.json
ble-continuity-regression-fixtures.zip
body-finder-validation-tools.zip
release-manifest.json
capability-matrix.json
protocol-version.txt
SBOM.spdx.json
SHA256SUMS
```

## 14. Physical acceptance gates

Run exactly five minutes with screens awake/app foreground:

```text
peer uptime >=99% preferred
usable metric range uptime >=90%
GEOMETRY_2D uptime >=90%
```

Fresh metric uptime is reported separately; it may be lower because bounded HOLDOVER is the mechanism under validation.

Truth gates:

```text
profile remains android-ble-lab-v1
invalid RSSI does not contaminate valid statistics
holdover never exceeds 10s
sigma never decreases in holdover
expired/out-of-domain/rejected edges do not enter solver
manual geometry remains disabled
human scanning remains blocked
rescue validation remains false
```

## 15. Definition of Done

The increment is complete only when:

1. invalid RSSI is filtered before the valid queue;
2. raw/valid/invalid sample accounting is separate;
3. diagnostics use valid-only RSSI median;
4. last-valid range cache exists;
5. FRESH/HOLDOVER/EXPIRED semantics are explicit;
6. HOLDOVER is bounded and sigma ages upward;
7. invalidating evidence clears/bypasses cached range;
8. global scan stall and isolated peer gap are distinguished;
9. scanner restart only responds to global callback silence;
10. solver accepts only FRESH/bounded HOLDOVER metric evidence;
11. temporal measurement health is exported/displayed;
12. validation-run export is internally consistent;
13. dev-6 physical profile/accuracy gates remain frozen;
14. all CI targets pass;
15. experimental.7 prerelease includes every mandatory artifact;
16. 5-minute physical continuity retest reaches usable metric uptime >=90% and 2D uptime >=90%;
17. human localization remains blocked until explicit review;
18. `rescue_use_validated=false`.
