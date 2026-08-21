# Body Finder – RuView
# IMPLEMENTATION PLAN — BLE Acquisition Continuity

> Baseline: `0.2.0-experimental.7` / `dev-7`
> Target: `0.2.0-experimental.8`
> Protocol: v2, additive only
> Scope: Android BLE callback acquisition continuity only
> Safety: experimental, not rescue validated, human scanning remains blocked until this gate passes

## 1. Executive decision

The `experimental.7` physical retest proved that the bounded `FRESH → HOLDOVER → EXPIRED` model behaves correctly, but it also isolated the remaining bottleneck: **per-peer Android BLE advertisement callback density is too irregular on Pixel 7/Pixel 10**, especially Pixel10↔Pixel7.

Observed physical evidence:

- peer/fabric uptime ≈ 99.9% on all three devices;
- `peer_expire_delta=0` on all three;
- foreground service and Wi-Fi/multicast/wake locks remained healthy;
- Lenovo fresh metric uptime ≈ 99.9%;
- Pixel 7 fresh metric uptime ≈ 47.8%, usable ≈ 85.1%;
- Pixel 10 fresh metric uptime ≈ 16.8%, usable ≈ 32.1%;
- 2D geometry uptime ≈ 60% across the three devices;
- RSSI sentinel filtering worked;
- bounded holdover worked and increased usable uptime without making stale edges immortal.

Therefore this increment MUST NOT solve the problem by:

- changing `RSSI@1m=-69.19`;
- changing `n=3.62`;
- expanding the validated 0.5–5.0 m domain;
- lowering `MIN_SAMPLES_FOR_RANGE=3`;
- expanding fresh window beyond 5 s;
- expanding holdover beyond 10 s;
- weakening reciprocal disagreement;
- modifying solver acceptance to manufacture 2D;
- increasing Tx power, because that would invalidate the calibrated RSSI-distance relationship.

The implementation target is to make the **existing valid estimator receive enough real BLE callbacks**.

---

## 2. Team size

Recommended logical team size: **7**.

1. TL — Tech Lead / Solution Architect
2. ABR — Android BLE Runtime Engineer
3. RRE — RF / Ranging Reliability Engineer
4. PGE — Protocol & Geometry Engineer
5. MUI — Mobile UX / Diagnostics Engineer
6. QAE — QA / Test Automation Engineer
7. DVE — DevOps / Release / Field Validation Engineer

Minimum viable staffing: 4 people by combining TL+PGE, ABR+RRE, MUI+QAE, and DVE.

---

## 3. Roles

### TL — Tech Lead / Solution Architect

Owns architecture, truthfulness, merge/release approval and invariant gates. Must reject any workaround that raises uptime only by keeping old measurements alive longer.

### ABR — Android BLE Runtime Engineer

Owns Android scanner settings, callback handling, acquisition counters, adaptive scanner behavior and API36 coexistence.

### RRE — RF / Ranging Reliability Engineer

Owns acquisition-quality definitions, callback/inter-arrival statistics, gap classification and acceptance thresholds. Calibration parameters are read-only.

### PGE — Protocol & Geometry Engineer

Owns additive diagnostic schema and verifies that acquisition changes do not alter metric graph semantics.

### MUI — Mobile UX / Diagnostics Engineer

Owns Expert diagnostics, report export, visible scan strategy and acquisition health.

### QAE — QA / Test Automation Engineer

Owns static contracts, regression fixtures, simulated acquisition timelines and physical acceptance analysis tooling.

### DVE — DevOps / Release / Field Validation Engineer

Owns CI, release artifacts, manifest, checksums, SBOM and physical retest instructions.

---

## 4. Frozen invariants

The following are immutable in `experimental.8`:

```text
profile_id                 android-ble-lab-v1
rssi_at_1m_dbm             -69.19
path_loss_exponent         3.62
validated                  true
valid_distance_min_m       0.5
valid_distance_max_m       5.0
physical_confidence        COARSE
MIN_SAMPLES_FOR_RANGE      3
RANGE_FRESHNESS_MS         5000
HOLDOVER_MAX_MS            10000
HARD_EXPIRY_MS             10000
HOLDOVER_SIGMA_AGING       0.15 m/s
```

---

## 5. Architecture changes

### 5.1 Software-filtered low-latency scan

Replace the normal Body Finder scan path from hardware manufacturer-data filtering to:

```text
Android BLE scan
  scanMode = LOW_LATENCY
  reportDelay = 0
  callbackType = ALL_MATCHES
  matchMode = AGGRESSIVE (API >= 23)
  numOfMatches = MAX_ADVERTISEMENT (API >= 23)
  filters = none
        ↓
Body Finder validates manufacturer id + BF payload in software
```

Reason: filtered/offloaded scanning can produce device/controller-specific callback suppression. Body Finder already validates its manufacturer payload in `recordScan`, so software filtering preserves correctness while reducing reliance on controller filter behavior.

No Tx-power change is allowed.

### 5.2 Explicit acquisition telemetry

For each BLE identity track:

```text
first_body_finder_seen_wall_ms
last_body_finder_seen_wall_ms
body_finder_callback_count
valid_rssi_callback_count
invalid_rssi_callback_count
last_interarrival_ms
mean_interarrival_ms
max_interarrival_ms
p50_interarrival_ms (bounded sample ring)
p95_interarrival_ms (bounded sample ring)
gap_gt_1s_count
gap_gt_2s_count
gap_gt_5s_count
gap_gt_10s_count
current_gap_ms
```

Also export validation-run scoped deltas where possible.

### 5.3 Scanner strategy truth

Expose:

```text
scan_strategy = SOFTWARE_FILTERED_ALL_MATCHES
hardware_filter_count = 0
match_mode = AGGRESSIVE or PLATFORM_DEFAULT
num_matches = MAX_ADVERTISEMENT or PLATFORM_DEFAULT
report_delay_ms = 0
```

### 5.4 Acquisition-health classification

Per peer:

```text
ACQUISITION_HEALTHY
ACQUISITION_SPARSE
ACQUISITION_GAP_2S
ACQUISITION_GAP_5S
ACQUISITION_GAP_10S
NO_BODY_FINDER_CALLBACK
```

This state is diagnostic only. It cannot itself create a metric edge.

### 5.5 API36 RangingManager coexistence

`RangingManager` has produced no physical range in Pixel 10 and showed hundreds of close events while commodity BLE scan is the currently validated metric source.

Implement a BLE-first coexistence policy:

- if a fresh real system range exists, system range remains preferred;
- if system ranging has produced no usable distance and repeatedly closes/fails, open a longer **BLE acquisition yield** window;
- while yielding, do not continuously recreate system sessions;
- BLE scanning/advertising remains active and independent;
- export `ble_yield_active`, `ble_yield_until_ms`, and `ble_yield_reason`;
- no fake system-ranging success is claimed.

Recommended initial yield: 120 s after repeated no-result/close behavior.

### 5.6 No per-peer scanner restart

Retain experimental.7 behavior:

- isolated peer gaps do not restart scanner;
- only global callback silence triggers scanner restart;
- cooldown remains bounded.

---

## 6. Acceptance targets

Physical 5-minute awake foreground run, same three Androids:

```text
all_peer_uptime_percent >= 99% preferred
usable_metric_range_uptime_percent >= 90% on ALL devices
geometry_2d_uptime_percent >= 90% on ALL devices
scan_restart_delta = 0 preferred
peer_expire_delta = 0
```

Additional acquisition target:

```text
for each observer→peer direction:
valid callback rate >= 0.6 Hz preferred
p95 inter-arrival <= 5 s preferred
no unexplained gap >10 s
```

These acquisition targets are diagnostic. The hard pass/fail remains usable metric and 2D uptime.

---

## 7. Atomic backlog

### EPIC A — Freeze baseline

| ID | Pri | Owner | Task | Acceptance |
|---|---|---|---|---|
| A-001 | P0 | TL | Freeze calibration constants | CI fails if changed |
| A-002 | P0 | TL | Freeze minSamples=3 | CI fails if changed |
| A-003 | P0 | TL | Freeze fresh=5s/holdover=10s | CI fails if changed |
| A-004 | P0 | QAE | Preserve dev-6 accuracy regression | PASS |
| A-005 | P0 | QAE | Preserve dev-7 holdover regression | PASS |

### EPIC B — Scanner strategy

| ID | Pri | Owner | Task | Acceptance |
|---|---|---|---|---|
| B-001 | P0 | ABR | Add centralized `BleAcquisitionPolicy` | Compiles |
| B-002 | P0 | ABR | Build low-latency settings | `LOW_LATENCY` |
| B-003 | P0 | ABR | Set `reportDelay=0` | Verified |
| B-004 | P0 | ABR | Set `CALLBACK_TYPE_ALL_MATCHES` | Verified |
| B-005 | P0 | ABR | Set `MATCH_MODE_AGGRESSIVE` API>=23 | Verified |
| B-006 | P0 | ABR | Set `MATCH_NUM_MAX_ADVERTISEMENT` API>=23 | Verified |
| B-007 | P0 | ABR | Start scan without hardware filters | Verified |
| B-008 | P0 | ABR | Keep software BF manufacturer/payload validation | Regression pass |
| B-009 | P0 | QAE | Static guard: primary scan has no manufacturer filter | PASS |

### EPIC C — Inter-arrival telemetry

| ID | Pri | Owner | Task | Acceptance |
|---|---|---|---|---|
| C-001 | P0 | ABR | Add per-identity previous callback timestamp | Exportable |
| C-002 | P0 | ABR | Add bounded interarrival ring | Max bounded |
| C-003 | P0 | ABR | Count valid callback events | Correct |
| C-004 | P0 | ABR | Count raw BF callback events | Correct |
| C-005 | P0 | ABR | Calculate current gap | Correct |
| C-006 | P0 | ABR | Calculate mean interval | Correct |
| C-007 | P0 | ABR | Calculate max interval | Correct |
| C-008 | P0 | ABR | Calculate p50 | Correct |
| C-009 | P0 | ABR | Calculate p95 | Correct |
| C-010 | P0 | ABR | Count gaps >1s | Correct |
| C-011 | P0 | ABR | Count gaps >2s | Correct |
| C-012 | P0 | ABR | Count gaps >5s | Correct |
| C-013 | P0 | ABR | Count gaps >10s | Correct |
| C-014 | P0 | QAE | Deterministic interval-stat tests | PASS |

### EPIC D — Acquisition health

| ID | Pri | Owner | Task | Acceptance |
|---|---|---|---|---|
| D-001 | P0 | RRE | Define healthy state | Spec |
| D-002 | P0 | RRE | Define sparse state | Spec |
| D-003 | P0 | RRE | Define gap states | Spec |
| D-004 | P0 | ABR | Implement classifier | Tests |
| D-005 | P0 | QAE | Timeline classification tests | PASS |

### EPIC E — RangingManager coexistence

| ID | Pri | Owner | Task | Acceptance |
|---|---|---|---|---|
| E-001 | P0 | ABR | Add no-result failure accounting | Diagnostic |
| E-002 | P0 | ABR | Add BLE-yield state | Diagnostic |
| E-003 | P0 | RRE | Set 120s initial yield | Constant |
| E-004 | P0 | ABR | Skip refresh during yield | Test/static contract |
| E-005 | P0 | ABR | Preserve fresh system result precedence | Regression |
| E-006 | P0 | QAE | Yield cannot clear BLE data | PASS |

### EPIC F — Diagnostics/export

| ID | Pri | Owner | Task | Acceptance |
|---|---|---|---|---|
| F-001 | P0 | MUI | Export scan strategy | JSON |
| F-002 | P0 | MUI | Export acquisition policy | JSON |
| F-003 | P0 | MUI | Export per-peer callback stats | JSON |
| F-004 | P0 | MUI | Export acquisition health | JSON |
| F-005 | P0 | MUI | Export RangingManager BLE-yield state | JSON |
| F-006 | P0 | QAE | Report schema regression | PASS |

### EPIC G — Validation run

| ID | Pri | Owner | Task | Acceptance |
|---|---|---|---|---|
| G-001 | P0 | ABR | Snapshot acquisition counters at run start | Stored |
| G-002 | P0 | ABR | Export callback deltas by run | JSON |
| G-003 | P0 | ABR | Export gap deltas by run | JSON |
| G-004 | P0 | QAE | Run-scoped counter tests | PASS |

### EPIC H — CI guards

| ID | Pri | Owner | Task | Acceptance |
|---|---|---|---|---|
| H-001 | P0 | DVE | Add acquisition contract checker | CI |
| H-002 | P0 | DVE | Guard unfiltered software scan | CI |
| H-003 | P0 | DVE | Guard aggressive match settings | CI |
| H-004 | P0 | DVE | Guard frozen profile | CI |
| H-005 | P0 | DVE | Guard minSamples/fresh/holdover | CI |
| H-006 | P0 | DVE | Guard human scanning false | CI |

### EPIC I — Version/release

| ID | Pri | Owner | Task | Acceptance |
|---|---|---|---|---|
| I-001 | P0 | MUI | Build string experimental.8 | UI/export |
| I-002 | P0 | MUI | report_version=10 | Export |
| I-003 | P0 | DVE | Android versionCode=8 | Manifest |
| I-004 | P0 | DVE | releaseIteration experimental.8 | app config |
| I-005 | P0 | DVE | Update release manifest | Truthful |
| I-006 | P0 | DVE | Add acquisition retest doc | Artifact |
| I-007 | P0 | DVE | Add plan to release | Artifact |
| I-008 | P0 | DVE | Build APK/AAB/legacy/Linux/Windows/iOS | Green |
| I-009 | P0 | DVE | Generate SBOM/SHA256 | Verified |

### EPIC J — Physical retest

| ID | Pri | Owner | Task | Acceptance |
|---|---|---|---|---|
| J-001 | P0 | DVE | Install identical universal APK on 3 Androids | Confirmed |
| J-002 | P0 | DVE | Use same non-collinear 0.5–5m layout | Confirmed |
| J-003 | P0 | DVE | Screens ON/foreground/power saver OFF | Confirmed |
| J-004 | P0 | DVE | Fresh 5-minute validation run | Complete |
| J-005 | P0 | DVE | End then export all 3 JSON | Complete |
| J-006 | P0 | RRE | Analyze per-direction callback density | Report |
| J-007 | P0 | RRE | Analyze p95 interarrival | Report |
| J-008 | P0 | RRE | Verify usable metric >=90% all devices | Gate |
| J-009 | P0 | RRE | Verify 2D >=90% all devices | Gate |
| J-010 | P0 | TL | Authorize/block next human-scene increment | Decision |

---

## 8. Definition of Done

The increment is complete only when:

1. calibration/profile/solver invariants remain unchanged;
2. primary Android scan is low-latency, all-matches, software-filtered;
3. API>=23 uses aggressive match mode and max advertisement matches;
4. RSSI invalid filtering remains prequeue;
5. per-direction callback and gap telemetry is exported;
6. acquisition-health state is visible in Expert diagnostics;
7. RangingManager yields after repeated no-result failures without disabling BLE;
8. system range still wins when a real fresh system range exists;
9. CI builds universal APK/AAB, legacy, Linux, Windows and iOS;
10. release manifest truthfully identifies experimental.8;
11. human scanning remains disabled;
12. a new prerelease is published with all mandatory artifacts;
13. physical retest instructions are included;
14. the final 5-minute physical retest reaches usable metric >=90% and Geometry 2D >=90% on all three devices before human-scene tests are unlocked.
