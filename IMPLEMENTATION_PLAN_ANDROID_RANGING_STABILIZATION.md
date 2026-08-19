# Body Finder – RuView: Android BLE/Ranging Stabilization Implementation Plan

> Repository: `Trochez/body_finder-RuView_WiFi-Mat`  
> Baseline: `main` at `2e61cbcb81a8536beaac16bec3c866c784d79bdb`  
> Target: `0.2.0-experimental.4`, protocol v2  
> Status: implementation/release execution plan  
> Source: physical findings from Pixel 10 Pro (API37), Pixel 7 Pro (API34), Lenovo TB-J606L (API30).

## 0. Executive decision

The first three-device physical test validated protocol v2, persistent node IDs, coordinator publication, automatic geometry refusal to fabricate coordinates, and zero manual X/Y/Z. It also exposed a blocking gap before the solver: no Android produced a usable pairwise range edge.

The implementation must stabilize and instrument this chain:

```text
UDP peer discovery
 -> protocol node_id + ble_identity
 -> Body Finder BLE advertisement recognition
 -> identity/address binding
 -> fresh per-peer RSSI samples
 -> PairwiseRangeObservation
 -> valid graph edge
 -> 2 nodes: 1D
 -> 3 nodes + 3 distance constraints: 2D
```

The solver must not be weakened to hide missing measurements.

## 1. Locked findings

### F-01 Lenovo API30 legacy Bluetooth permission failure

Observed: `Need BLUETOOTH permission` while using the universal APK. Required correction: declare legacy `BLUETOOTH` and `BLUETOOTH_ADMIN`, retain fine location for API<=30, and retain modern Nearby Bluetooth permissions for API31+.

### F-02 UDP discovery without pairwise ranging

Pixel 7 and Lenovo discovered protocol-v2 peers but exported empty `ranges`, `range_observations` and `valid_edge_pairs`.

### F-03 capability false-positive

`ble_peer_ranging=WORKING_DEGRADED` could be emitted merely because the BLE scanner had started. A live/degraded ranging claim must require Body Finder peer evidence and eventually a fresh range.

### F-04 insufficient BLE diagnostics

The first build did not expose per-peer advertisement count, identity match, BLE address binding, RSSI sample count/age, or exact no-range reason.

### F-05 API36+ lifecycle/fallback

Pixel 10 exposed Android `RangingManager` states including awaiting binding and a closed session. System ranging is preferred only when it produces a fresh valid result; BLE scan RSSI fallback must stay independent.

### F-06 fabric stability not diagnosable

Pixel 10 showed three nodes in one snapshot and later zero peers. Before changing timeouts, the build must expose UDP packet counters, last-seen age and expirations.

### F-07 Pixel status-bar/safe-area overlap

UI must respect Android status/cutout area without model whitelists.

### Not confirmed

An earlier Pixel 10 text export arrived truncated, but a later complete JSON proved truncation is not a confirmed application defect. Result export may be improved but is not the ranging root cause.

## 2. Product constraints

1. No normal-flow manual node coordinates.
2. Protocol remains v2 unless a breaking wire change becomes unavoidable.
3. No model whitelist; runtime capability probing only.
4. BLE RSSI remains low-confidence with conservative sigma.
5. Wi-Fi connected-link RSSI is not phone-to-phone ranging.
6. CSI/UWB/BLE-CS/RTT must never be claimed live without real source evidence.
7. Missing/stale measurement means insufficient/degraded geometry, never default coordinates.
8. Build remains experimental and not validated for rescue use.

## 3. Team and roles

### TL — Tech Lead / Solution Architect

Owns architecture, scope, truthfulness, cross-layer review, CI/release acceptance and go/no-go for human testing.

### ARF — Android RF/BLE/Ranging Engineer

Owns Android permissions, scan/advertise, manufacturer payload, identity/address binding, RSSI windows, API36 RangingManager, fallback and native RF diagnostics.

### MUI — React Native / Mobile UI Engineer

Owns permission UX, Expert diagnostics, safe area, report schema/export and user-visible truth states.

### PGE — Protocol & Geometry Engineer

Owns protocol-v2 range contracts, validation, stale/replay/session rules, graph edges and protection of 1D/2D observability semantics.

### QAE — QA / Test Automation Engineer

Owns regression fixtures, contract tests, API-level matrix, CI test cases and physical test checklist.

### DRE — DevOps / Release Engineer

Owns CI, packaging, checksum, SBOM, prerelease assets, release manifest and failure-on-missing-artifact gates.

### VDE — Validation / Data Engineer

Owns interpretation of physical JSON, binding/range availability metrics and comparison to external ground truth after automatic solving.

### FTL — Field Test Lead

Owns homogeneous installation on physical devices, permissions/settings, test placement, screenshots/exports and ground-truth measurement only after solve.

## 4. RACI

| Area | Accountable | Responsible | Consulted |
|---|---|---|---|
| Architecture | TL | TL | ARF/PGE/MUI |
| Android permissions | TL | ARF | MUI/QAE |
| BLE scan/advertise | TL | ARF | QAE |
| Identity binding | TL | ARF | PGE/QAE |
| API36 ranging | TL | ARF | QAE |
| Range/geometry validation | TL | PGE | ARF/QAE |
| Expert diagnostics/UI | TL | MUI | ARF/VDE |
| UDP diagnostics | TL | ARF | PGE/QAE |
| Test automation | QAE | QAE | ARF/PGE/MUI |
| CI/release | DRE | DRE | TL/QAE |
| Physical retest | FTL | FTL | QAE/VDE |
| Acceptance | TL | VDE | ARF/PGE/QAE |

## 5. Target runtime state model

BLE adapter, scan, advertise, binding, system ranging and pairwise-range states must be independently observable. Minimum semantic states:

```text
scan: IDLE / STARTING / ACTIVE_NO_BODY_FINDER_PEER / ACTIVE_PEER_SEEN / FAILED
advertise: IDLE / STARTING / ACTIVE / UNSUPPORTED / FAILED
binding: UDP_ONLY / BLE_IDENTITY_KNOWN / BLE_IDENTITY_SEEN / SAMPLES_ACQUIRING / RANGE_READY
system ranging: READY_NO_BOUND_PEER / STARTING / ACTIVE_NO_RESULT / ACTIVE_RESULT / OPEN_FAILED / CLOSED / BACKOFF / FAILED
```

## 6. Required BLE diagnostics

Per-device:

```text
scan_state
advertise_state
scan_mode
total_scan_results
body_finder_scan_results
malformed_body_finder_payloads
self_scan_results_ignored
last_any_scan_result_age_ms
last_body_finder_scan_result_age_ms
```

Per peer:

```text
node_id
ble_identity
address_fingerprint (never raw exported MAC)
binding_state
body_finder_scan_results_for_identity
sample_count_5s
sample_count_8s
last_sample_age_ms
latest_rssi_dbm
median_rssi_dbm
median_tx_power_dbm
fallback_range_ready
address_rebind_count
blocking_reason
```

System ranging diagnostics:

```text
state
requested_peer_count
active_peer_count
result_count
last_result_age_ms
last_close_reason
last_open_failure_reason
last_error
retry_in_ms
fresh_result_available
```

## 7. BLE scan strategy

Use explicit foreground test settings:

```text
SCAN_MODE_LOW_LATENCY
reportDelay = 0
manufacturer id = 0x05F1
payload prefix = 0x42 0x46
```

Prefer filtered scan. If the device stack rejects the filter synchronously, fall back to unfiltered low-latency scan and record the degradation.

## 8. Identity binding

Only bind a protocol node to a BLE endpoint when:

```text
UDP peer ble_identity == manufacturer-data ble_identity
```

Never bind by device name, model, discovery order or RSSI similarity. Android private addresses may rotate; preserve node identity and update endpoint binding. Export only a session-derived hash of the address.

## 9. BLE RSSI fallback

Constants for this validation build:

```text
window retention = 8000 ms
fresh range window = 5000 ms
minimum samples = 3
maximum retained samples = 21
path-loss n = 2.2
minimum conservative sigma = 1.5 m
```

Do not tune the path-loss model for apparent accuracy in this release. The goal is measurement plumbing and observability.

A fallback observation must preserve:

```text
session_id
observer_node_id
peer_node_id
technology=BLE_RSSI
monotonic_ns
distance_m
distance_sigma_m
rssi_dbm
quality=LOW
source_detail
```

## 10. API36+ RangingManager rules

System result wins only when fresh and containing a finite distance. `onOpenFailed` or `onClosed` must release the dead session/fingerprint so refresh can retry after bounded backoff. Those callbacks must never clear BLE scan RSSI windows.

Numeric Android reason codes are exported raw. Symbolic interpretation is allowed only when guaranteed by the SDK; never guess.

## 11. Capability truth

```text
scanner active + no Body Finder advertisement -> SUPPORTED_UNVERIFIED / ACQUIRING
Body Finder peer advertisement seen -> degraded acquiring
>=3 fresh samples + emitted BLE_RSSI range -> WORKING_DEGRADED / LIVE_BLE_RSSI
fresh API36 real distance -> technology-specific live result
```

Scanner startup alone is not a live ranging claim.

## 12. UDP fabric diagnostics

Expose socket state, multicast join state, TX/RX counters, protocol-v2 packet count, same-session packet count, active peer count, peer-expire count, and per-peer packet count/last-seen age.

Do not change the 5-second peer timeout until a physical retest proves that the timeout itself is the cause of useful-peer loss.

## 13. Geometry protection

Existing solver requirements remain:

```text
2 nodes + 0 edges -> insufficient
2 nodes + 1 valid distance -> 1D only
3 nodes + 2 distance edges -> not enough for unique 2D triangle
3 nodes + 3 non-degenerate distance edges -> 2D candidate
stale/replayed/invalid edges -> rejected
```

## 14. UI requirements

Expert must expose BLE/ranging diagnostics and fabric diagnostics directly, without ADB. Radar may add `BLE PEERS` alongside actual `RANGE` count. Safe-area layout must avoid status-bar overlap on Pixel devices without per-model padding.

## 15. Report requirements

Target report version 6. It must contain:

```text
build=0.2.0-experimental.4
protocol_version=2
manual_geometry_override=false
capabilities
ble_diagnostics
fabric_diagnostics
local
peers
geometry
graph_diagnostics
range_observations
```

## 16. Atomic backlog by owner

### ARF / P0

- declare API30 legacy Bluetooth permissions;
- retain API31+ scan/connect/advertise permissions;
- validate API30 fine-location path;
- implement low-latency filtered scan;
- count all/Body Finder/malformed/self scan results;
- track last scan ages;
- track advertise state/failure;
- implement exact `ble_identity` binding;
- hash exported BLE address;
- track address rebinding;
- expose 5s/8s sample windows;
- enforce 3 fresh sample minimum;
- emit independent BLE_RSSI fallback observation;
- implement per-peer blocking reason;
- release failed/closed API36 sessions;
- add retry backoff;
- expose system-ranging lifecycle counters;
- keep fallback independent;
- instrument UDP packet/last-seen/expiry.

### MUI / P0-P1

- request runtime permissions by API level;
- poll native diagnostics;
- show BLE and fabric sections in Expert;
- show BLE peer count;
- include diagnostics in report v6;
- update build label to experimental.4;
- fix Android top safe area/status bar.

### PGE / P0

- preserve session/observer identity validation;
- preserve finite positive distance/sigma checks;
- preserve source/technology provenance;
- preserve stale/replay rejection;
- preserve reciprocal pair aggregation;
- preserve 1D/2D observability thresholds.

### QAE / P0-P1

- add first-test regression fixtures for API30/API34/API37;
- add automated Android ranging contract check;
- validate JSON fixtures;
- enforce generated manifest permissions;
- define two-Pixel 60-second gate;
- define three-Android 90-second gate;
- define five-minute stability gate;
- require JSON/screenshots before blind retry.

### DRE / P0-P1

- run contract checks in CI;
- build universal APK/AAB and legacy APK;
- keep Linux/Windows/iOS regression builds;
- package retest instructions;
- package stabilization plan;
- package Android diagnostics fixtures;
- update release manifest/version/classification;
- regenerate SBOM and SHA256SUMS;
- fail release if required assets are missing;
- publish new `dev-*` prerelease after main merge.

### VDE + FTL / physical gate

- T0 truth/permission check on each Android;
- T1 Pixel10+Pixel7 <=3m for 60s;
- require >=1 real pairwise edge and 1D;
- T2 add Lenovo in non-collinear triangle for 90s;
- require three unique distance edges for a fully constrained triangle when no angle source exists;
- measure pairwise ground truth only after automatic solve;
- T3/T4 stability and availability metrics;
- return JSON + screenshots.

## 17. CI gates

### G0 build

All existing Rust, Android full, Android legacy and iOS simulator jobs pass.

### G1 permissions

Generated Android manifest contains legacy and modern Bluetooth permission families.

### G2 acquisition contract

Source/contract checks verify low-latency scan, manufacturer filter, counters, binding diagnostics, 3-sample/freshness gates and independent fallback.

### G3 geometry regression

Workspace tests preserve 1D/2D/stale/replay behavior.

### G4 release completeness

Required Android/Linux/Windows artifacts, plan, retest guide, manifests, diagnostics fixtures, SBOM and checksums exist and are non-empty.

## 18. Physical acceptance sequence

### T0

Each device separately: build .4, protocol 2, no manual coordinate UI, new diagnostics present. Lenovo must not emit the prior missing-BLUETOOTH-permission exception.

### T1

Pixel 10 + Pixel 7, foreground, 1–3m apart, 60 seconds. Pass requires at least one Body Finder identity match, >=3 fresh samples, one pairwise range edge and 1D geometry.

### T2

Add Lenovo in triangle, 90 seconds. Pass requires legacy-permission issue closed and all constraints needed for 2D. Missing constraint is a valid failure only when Expert explains its stage.

### T3

After automatic solve, measure external pairwise distances. Never feed them back to the application.

### T4

Five-minute stability: inspect peer expiry, last-seen age, rebinds, sample freshness, range availability and geometry state.

## 19. Release artifacts

Required stabilization prerelease additions:

```text
IMPLEMENTATION_PLAN_ANDROID_RANGING_STABILIZATION.md
ANDROID_RANGING_RETEST.md
android-ranging-diagnostics-fixtures.zip
```

Retain existing automatic-geometry release artifacts:

```text
body-finder-ruview-universal.apk
body-finder-ruview.aab
body-finder-ruview-legacy-minsdk21.apk
body-finder-node-linux-x86_64.tar.gz
body-finder-node-linux-x86_64.deb
body-finder-node-windows-x86_64.zip
body-finder-ruview-ios-simulator.zip
body-finder-validation-tools.zip
TESTING_AUTOGEOMETRY_RELEASE.md
release-manifest.json
capability-matrix.json
protocol-version.txt
ruview-upstream-lock.json
model-manifest.json
SBOM.spdx.json
SHA256SUMS
```

## 20. Definition of Done

The software increment is complete when:

- Lenovo API30 missing-legacy-permission defect is fixed;
- scanner startup is no longer mislabeled as live ranging;
- BLE acquisition/binding/sample blocker is visible per peer;
- system-ranging failure is retryable and does not kill fallback;
- UDP disappearance is diagnosable;
- safe-area overlap is corrected;
- report v6 includes new diagnostics;
- CI is green;
- a new prerelease is published with all mandatory artifacts.

The wider human/LOS/wall campaign remains blocked until the new physical T1/T2 gates pass. Software completion is not a claim of rescue or through-wall performance validation.
