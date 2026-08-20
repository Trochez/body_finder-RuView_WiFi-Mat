# Body Finder – RuView — `android-ble-lab-v1` metric implementation plan

**Target:** `0.2.0-experimental.6`  
**Protocol:** v2, additive compatibility  
**Status:** implementation source of truth  
**Safety:** experimental only; human localization, through-wall and rescue use remain unvalidated.

## 1. Accepted physical profile

The completed P0c physical campaign (3 Android pairs × 5 distances × both directions) passed the previously defined experimental metric gate. Runtime ground truth remains prohibited.

```text
profile_id: android-ble-lab-v1
RSSI@1m: -69.19 dBm
path-loss exponent n: 3.62
validated: true
valid distance: 0.5–5.0 m
physical confidence: COARSE
```

Validation evidence locked in `validation/fixtures/ble-range/p0c-calibration-summary.json`:

```text
leave-one-distance-out MAE: 0.85 m
RMSE: 1.11 m
max error: 2.58 m
reciprocal-fused MAE: 0.83 m
reciprocal-fused RMSE: 1.07 m
reciprocal-fused max error: 2.30 m
```

## 2. Non-negotiable behavior

- Metric BLE RSSI is enabled only for a **validated** profile and only when the raw model estimate lies inside 0.5–5.0 m.
- Outside-domain estimates return `distance_m=null`, `metric_valid=false`; there is no silent clamp.
- Android RSSI sentinel `127` and invalid RF values are excluded before statistics and calibration export.
- Advertised TxPower remains diagnostic only; it is never substituted for RSSI@1m.
- Pairwise reciprocal A→B and B→A observations are fused before the solver when both are fresh and valid.
- Reciprocal disagreement inflates uncertainty or rejects the pair.
- Single-direction metric fallback is allowed only with conservative sigma inflation.
- BLE-only physical confidence cannot exceed `COARSE`.
- Manual X/Y/Z remains absent from normal operation.
- Ground truth never enters the runtime solver.

## 3. Team size and roles

Recommended logical team size: **8**.

| Role | Owner code | Responsibility |
|---|---|---|
| Tech Lead / Solution Architect | TL | Architecture, truthfulness, acceptance and release decision |
| Android BLE/RF Engineer | ARF | RSSI filtering, estimator, runtime profile, system-range precedence |
| RF Calibration & Data Engineer | RDE | Profile parameters, sigma, disagreement gates, physical analysis |
| Protocol & Geometry Engineer | PGE | Reciprocal fusion, metric graph gating, solver inputs and provenance |
| React Native / Mobile UX Engineer | MUI | Radar/Expert truth, exports and report versioning |
| QA / Test Automation Engineer | QAE | Regression fixtures, contract tests and acceptance tests |
| DevOps / Release Engineer | DRE | CI, packaging, release manifest, checksums and SBOM |
| Field Validation Engineer | FVE | Three-node physical retest and external measurements |

Minimum viable team: 4 people combining TL+PGE, ARF+RDE, MUI+QAE, DRE+FVE.

## 4. Atomic backlog

### A — Calibrated profile

- **A-01 / RDE / P0:** version `android-ble-lab-v1` with exact accepted parameters.
- **A-02 / RDE / P0:** set `validated=true`, confidence `COARSE`, domain 0.5–5.0 m.
- **A-03 / DRE / P0:** include profile and hash in release artifacts.
- **A-04 / QAE / P0:** schema validates active and historical profiles.

### B — RSSI safety and estimator

- **B-01 / ARF / P0:** centralize valid RSSI predicate.
- **B-02 / ARF / P0:** reject sentinel `127` before median/model.
- **B-03 / MUI / P0:** remove invalid RSSI from exported calibration snapshots.
- **B-04 / ARF / P0:** compute raw distance with RSSI@1m=-69.19 and n=3.62.
- **B-05 / ARF / P0:** `OUT_OF_DOMAIN_LOW/HIGH` emit null metric distance.
- **B-06 / QAE / P0:** regression proves no silent 0.5/5/30 m clamp.

### C — Conservative uncertainty

- **C-01 / RDE / P0:** validation RMSE/MAE provides model floor.
- **C-02 / ARF / P0:** propagate robust RSSI sample noise and profile uncertainty.
- **C-03 / PGE / P0:** solver receives source/fused sigma without replacing it with an optimistic default.
- **C-04 / QAE / P0:** sigma is finite and never zero; higher sample noise increases sigma.

### D — Reciprocal fusion

- **D-01 / PGE / P0:** canonical pair grouping A↔B by session and technology.
- **D-02 / PGE / P0:** latest fresh observation per direction.
- **D-03 / PGE / P0:** inverse-variance reciprocal fusion.
- **D-04 / RDE / P0:** degraded/reject disagreement thresholds.
- **D-05 / PGE / P0:** rejected disagreement never creates a metric edge.
- **D-06 / PGE / P0:** single-direction fallback inflates sigma.
- **D-07 / QAE / P0:** deterministic agreement/degraded/reject/single-direction tests.

### E — Provenance and graph truth

- **E-01 / PGE / P0:** raw range carries profile id, validation state, raw distance and status.
- **E-02 / PGE / P0:** fused edge carries fusion mode, source count, source observers and reciprocal delta.
- **E-03 / PGE / P0:** graph only accepts `metric_valid=true` finite observations.
- **E-04 / PGE / P0:** out-of-domain, invalid RSSI, proximity-only and reciprocal reject remain non-metric.
- **E-05 / PGE / P0:** `MeasurementHealth` reports metric/proximity/out-of-domain/disagreement counts.
- **E-06 / QAE / P0:** three valid non-degenerate metric pairs are eligible for 2D; fewer constraints cannot fabricate 2D.

### F — UI and export

- **F-01 / MUI / P0:** bump app to experimental.6 / report v8.
- **F-02 / MUI / P0:** Expert states validated coarse profile and 0.5–5.0 m boundary.
- **F-03 / MUI / P0:** Radar shows metric/proximity counts and physical confidence.
- **F-04 / MUI / P0:** export raw observations and fused observations separately.
- **F-05 / MUI / P0:** export reciprocal fusion diagnostics and measurement health.
- **F-06 / QAE / P0:** no UI wording presents graph condition as physical accuracy.

### G — Source precedence

- **G-01 / ARF / P0:** fresh Android system range remains preferred when available.
- **G-02 / PGE / P0:** stale system range does not block validated BLE metric fallback.
- **G-03 / QAE / P0:** system/ BLE precedence regression tests.

### H — CI and release

- **H-01 / QAE / P0:** contract checker locks exact profile values and P0c gates.
- **H-02 / QAE / P0:** checker locks RSSI sentinel filtering and no-clamp behavior.
- **H-03 / QAE / P0:** checker locks reciprocal fusion and graph gating.
- **H-04 / DRE / P0:** Android APK/AAB, legacy APK, Linux, Windows and iOS Simulator builds remain green.
- **H-05 / DRE / P0:** release fails if mandatory validation/profile/retest artifacts are absent.
- **H-06 / DRE / P0:** manifest states profile validated/coarse and human/rescue false.
- **H-07 / DRE / P0:** SHA256 and SBOM generated and verified.

### I — Physical acceptance

- **I-01 / FVE / P0:** install same experimental.6 APK on Pixel 10 Pro, Pixel 7 Pro and Lenovo TB-J606L.
- **I-02 / FVE / P0:** non-collinear triangle with all true pair distances inside 0.5–5.0 m.
- **I-03 / FVE / P0:** 90-second validation run; export 3 JSONs and screenshots.
- **I-04 / FVE / P0:** measure three pair distances only after export.
- **I-05 / RDE / P0:** calculate pairwise MAE and max error.
- **I-06 / PGE / P0:** confirm three metric pairs, 3/3 positions and 2D solution.
- **I-07 / TL / P0:** human-presence test authorization only if the metric geometry gate passes.

## 5. Acceptance gates

### Software gate

```text
active profile = android-ble-lab-v1
validated = true
RSSI@1m = -69.19
n = 3.62
domain = 0.5–5.0 m
physical confidence = COARSE
no silent clamp
RSSI 127 excluded
reciprocal fusion enabled
manual geometry override = false
protocol = 2
```

### Physical three-node gate

```text
3 active nodes
3 unique metric pair constraints
GEOMETRY_2D
3/3 nodes positioned
physical confidence <= COARSE
pairwise MAE <= 2.0 m
maximum pair error <= 3.0 m
```

A negative out-of-domain result is valid and must not be forced into the graph.

## 6. Release artifacts

Mandatory additions for experimental.6:

```text
IMPLEMENTATION_PLAN_ANDROID_BLE_LAB_V1_METRIC.md
ANDROID_BLE_METRIC_GEOMETRY_RETEST.md
ble-range-calibration-profiles.json
ble-range-calibration-schema.json
ble-range-calibration-fixtures.zip
body-finder-validation-tools.zip
release-manifest.json
capability-matrix.json
SHA256SUMS
SBOM.spdx.json
```

Existing Android/Linux/Windows/iOS-simulator artifacts remain mandatory.

## 7. Definition of Done

The increment is done only when CI is fully green, the prerelease is published with all mandatory artifacts, and the three-node physical retest can be executed without manual coordinates. Passing the software build does **not** itself authorize human/rescue claims.
