# Body Finder – RuView / WiFi-Mat Implementation Plan

> **Repository:** `Trochez/body_finder-RuView_WiFi-Mat`  
> **Product name:** **Body Finder – RuView**  
> **Plan date:** 2026-08-16  
> **Primary upstream:** `ruvnet/RuView`  
> **Upstream snapshot reviewed:** `4685618388a5e49fad5b3005806f3bdd6a7c25c3`  
> **Primary goal:** automatically use the capabilities of ordinary Android, iOS, and Ubuntu devices to detect human-presence evidence through walls/debris and estimate the relative position of each detected human, with explicit confidence and uncertainty.  
> **Execution target:** this document is written primarily for autonomous execution by Codex through small, testable PRs and `dev-N` prereleases.

---

## 0. Executive decision

Body Finder must **not** assume that an arbitrary phone exposes Wi-Fi Channel State Information (CSI). Instead, every device is dynamically capability-probed and contributes whatever measurements it can actually produce.

The system therefore has two complementary sensing paths:

1. **Common-device path — mandatory**
   - Android phones/tablets, iPhone/iPad, Ubuntu laptops/desktops.
   - Wi-Fi RSSI/link metrics where the OS exposes them.
   - Wi-Fi RTT / FTM when supported.
   - BLE RSSI/ranging evidence.
   - IMU/orientation/motion.
   - Optional camera-assisted **sensor geometry calibration only**; camera is never the through-wall detector.
   - Multi-link radio-tomographic / device-free localization experiments.

2. **CSI-enhanced path — optional and automatically enabled only when real CSI is detected**
   - Compatible Ubuntu Wi-Fi hardware/drivers or other future CSI-capable devices.
   - RuView `wifi-densepose-hardware`, `wifi-densepose-signal`, `wifi-densepose-vitals`, and WiFi-Mat integration.
   - No dedicated ESP32 hardware is required for this project or for the v1 common-device validation lab.
   - Optional ESP32 firmware artifacts may still be built for compatibility with RuView, but **they are not a dependency of the Body Finder product or v1 acceptance tests**.

The primary UI result is always the **best relative position estimate currently justified by evidence**, even when uncertainty is high. Poor estimates must be visually represented as poor estimates; they must never be drawn as exact points without uncertainty.

---

# 1. Product mission

Build a field-ready, offline-capable application that can be installed on:

- Android phones and tablets,
- iPhone/iPad,
- Ubuntu x86_64 and arm64 devices,

and can automatically form a local sensing group from the devices available at the scene.

The main product question is:

> **“Where is each possible human relative to the operator/sensor array, and how uncertain is that estimate?”**

The target output for each tracked person is:

```text
Possible Human #2

RELATIVE POSITION
x = +2.8 m
y = -1.1 m
z = -0.7 m

Distance              3.1 m
Direction             21° right
Estimated depth       ~0.7 m

Human confidence       84%
Position uncertainty   27%
Estimated error        ±1.2 m (95% region)
Evidence quality       MEDIUM

Track                  PROBABLE HUMAN
Evidence               RSSI + RTT + geometry + temporal motion
```

The default visualization is a **radar**, with synchronized **2D map** and **3D** views.

---

# 2. Locked product decisions from the design interview

These decisions are requirements unless a later documented ADR explicitly supersedes them.

## 2.1 Platforms

- Android + iOS + Ubuntu are official targets.
- Current physical lab:
  - Google Pixel 7 Pro,
  - Google Pixel 10 Pro,
  - Lenovo Tab2,
  - one native Ubuntu device,
  - one Ubuntu-under-WSL/Windows device.
- There must be **no Android model whitelist**. Support is determined by OS/runtime and functional capability probes.
- The WSL device starts as a compute/development node and may only be promoted to RF sensing if functional probes demonstrate useful direct radio access.

## 2.2 Common-device first

- Body Finder must run without dedicated CSI hardware.
- Android without CSI remains useful as display, compute, network node, geometry/ranging node, and radio-measurement node where APIs permit.
- True CSI processing is enabled only if a device actually proves CSI capability.
- Root/custom drivers are optional advanced adapters, never required for ordinary operation.

## 2.3 Offline operation

- No Internet required.
- No cloud account required.
- No login required.
- Network cascade:
  1. use an existing local LAN if appropriate,
  2. otherwise create an Ubuntu hotspot,
  3. otherwise create an Android Local-Only Hotspot,
  4. use platform peer-to-peer capabilities if available,
  5. degrade to BLE/control-only connectivity when necessary.
- The field network may be open/no manual pairing for rapid deployment, per product decision.
- Because an open RF network is spoofable, the UI must expose `NETWORK: OPEN/UNTRUSTED` and the protocol must still use session IDs, sequence numbers, monotonic timestamps, replay rejection, checksums, and strict parsing. Do **not** claim cryptographic authenticity in open mode.

## 2.4 Automatic fabric

The normal operator workflow is:

```text
OPEN APP
   ↓
DISCOVER DEVICES
   ↓
FUNCTIONAL CAPABILITY PROBES
   ↓
ELECT COORDINATOR
   ↓
FORM LOCAL SENSOR FABRIC
   ↓
ESTIMATE SENSOR GEOMETRY
   ↓
CALIBRATE BACKGROUND
   ↓
START HUMAN SEARCH
   ↓
FUSE EVIDENCE
   ↓
DISPLAY RELATIVE TARGET POSITIONS + UNCERTAINTY
```

- Devices joining after scanning begins are incorporated without restarting the session.
- Devices disappearing cause automatic graph reconfiguration and uncertainty inflation, not a reset.
- Coordinator failover must preserve session state and active tracks.

## 2.5 Human detection semantics

The product must **not** equate “no detectable breathing/movement” with “deceased.”

Use track states:

```text
SIGNAL
  ↓
POSSIBLE HUMAN
  ↓
PROBABLE HUMAN
  ↓
CONFIRMED TRACK
  ↓
LOST / REACQUIRED
```

If several targets cannot be resolved reliably, show:

```text
POSSIBLE CLUSTER: 2–3 HUMANS
```

rather than manufacturing individual IDs.

## 2.6 Localization quality

Engineering localization tiers:

| Tier | Empirical position error target |
|---|---:|
| GOLD | ≤ 0.5 m |
| GOOD | ≤ 1.0 m |
| USABLE | ≤ 2.0 m |
| COARSE | ≤ 5.0 m |
| PRESENCE | position cannot be responsibly resolved |

The desired v1 engineering target is **GOOD (≤1 m)** in sufficiently capable configurations, but the application may operate at any tier and must report the tier honestly.

Initial visual uncertainty bands:

| Uncertainty | Label |
|---:|---|
| 0–20% | HIGH precision |
| 20–40% | MEDIUM precision |
| 40–70% | LOW precision |
| >70% | VERY LOW / approximate only |

These thresholds are provisional. Replace them with empirically calibrated thresholds after the ground-truth dataset exists.

---

# 3. Truth, safety, and claim policy

This is a search-and-rescue-oriented sensing tool. False certainty is more dangerous than an explicit weak result.

## 3.1 Non-negotiable rules

1. **Never label simulated data as live data.**
2. **Never label RSSI as CSI.**
3. **Never report a feature as supported based only on device model. Run a functional probe.**
4. **Never report a point location without its uncertainty region.**
5. **Never infer “deceased” solely from absent radio-observed motion/vitals.**
6. **Never treat a negative scan as proof that no human is present.**
7. **Never copy performance numbers from RuView documentation into Body Finder product claims until independently reproduced in the Body Finder testbed.**
8. Every target must expose evidence provenance in Expert mode.
9. Store the exact app version, model versions, upstream RuView commit, node topology, and calibration metadata with every recorded test.

## 3.2 Product wording

Preferred:

- “Possible human”
- “Probable human”
- “Human-presence evidence”
- “Estimated relative position”
- “Approximate depth”
- “Confidence”
- “Uncertainty”

Avoid unless independently validated for the exact capability path:

- “See any body through any wall”
- “Guaranteed survivor detection”
- “Exact position”
- “No person present” based only on a negative RF scan
- “Deceased” based only on missing RF vitals

---

# 4. Upstream RuView integration strategy

## 4.1 Pin, adapt, do not fork blindly

Use RuView through a compatibility layer pinned to an exact commit.

Create:

```text
upstream/
  ruvieW.lock.json
  COMPATIBILITY.md
```

`ruvieW.lock.json` should include at minimum:

```json
{
  "repository": "https://github.com/ruvnet/RuView",
  "commit": "4685618388a5e49fad5b3005806f3bdd6a7c25c3",
  "reviewed_at": "2026-08-16",
  "required_components": [
    "wifi-densepose-core",
    "wifi-densepose-signal",
    "wifi-densepose-hardware",
    "wifi-densepose-vitals",
    "wifi-densepose-mat",
    "wifi-densepose-wifiscan"
  ]
}
```

The bootstrap phase may update the pinned SHA if upstream has moved, but only after the compatibility suite passes. Record every update in `COMPATIBILITY.md`.

## 4.2 Relevant upstream components

Primary candidates:

```text
RuView/v2/crates/wifi-densepose-core
RuView/v2/crates/wifi-densepose-signal
RuView/v2/crates/wifi-densepose-hardware
RuView/v2/crates/wifi-densepose-vitals
RuView/v2/crates/wifi-densepose-mat
RuView/v2/crates/wifi-densepose-wifiscan
RuView/ui/mobile
```

Use RuView's WiFi-Mat domain concepts where they are implemented and testable, but wrap them behind Body Finder interfaces so an upstream change cannot propagate throughout the app.

## 4.3 Mandatory upstream audit

Before integrating a RuView feature, classify it as one of:

```text
VERIFIED_REAL
REAL_BUT_UNVALIDATED_HERE
SIMULATED
STUB
DOCUMENTATION_ONLY
DEPRECATED
```

Store the result in:

```text
docs/RUVIEW_TRUTH_MATRIX.md
```

Every `VERIFIED_REAL` classification must point to:

- source code,
- tests,
- an executable path,
- and, for physical sensing claims, a Body Finder physical test recording.

## 4.4 Mobile dependency reconciliation

Do not copy the upstream mobile `package.json` blindly.

At the reviewed snapshot, RuView declares Expo SDK 55 while its mobile package also declares a React Native version that does not match Expo's documented SDK-55 pairing. Phase 0 must reproduce the upstream mobile build and then pin a known-good combination before Body Finder code is added.

Priority:

1. reproduce upstream exactly,
2. if broken, align dependencies to the supported Expo/RN matrix,
3. add tests,
4. only then consider upgrading Expo,
5. never combine a framework migration with sensing changes in the same PR.

---

# 5. Target architecture

```text
┌───────────────────────────────────────────────────────────────┐
│                  BODY FINDER – RuView                         │
├───────────────────────────────────────────────────────────────┤
│ Operator UI: Radar | 2D | 3D | Operator | Expert | EN/ES     │
└──────────────────────────────┬────────────────────────────────┘
                               │
                     Session / Track Store
                               │
                 ┌─────────────▼─────────────┐
                 │   Human Fusion Engine     │
                 │ existence + position +    │
                 │ covariance + provenance   │
                 └─────────────┬─────────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
     Commodity DFL/RTI      CSI/RuView      Geometry Engine
      RSSI/RTT/BLE          if present     RTT/BLE/IMU/visual
              │                │                │
              └────────────────┼────────────────┘
                               ▼
                    Normalized Evidence Bus
                               │
                  Sensor Fabric / Time Sync
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
       Android                iOS                Ubuntu
   Kotlin native probes   Swift native probes  Rust/Linux probes
   RSSI/RTT/BLE/IMU       BLE/IMU/network     RSSI/iw/nl80211
   hotspot/compute        UI/compute          optional CSI
          │                    │                    │
          └────────────────────┴────────────────────┘
                     offline local network
```

---

# 6. Repository structure

Create this monorepo structure progressively; do not scaffold unused modules before their phase.

```text
body_finder-RuView_WiFi-Mat/
├── IMPLEMENTATION_PLAN.md
├── README.md
├── LICENSE
├── NOTICE.md
├── Cargo.toml
├── rust-toolchain.toml
├── package.json
├── pnpm-workspace.yaml
│
├── upstream/
│   ├── ruvieW.lock.json
│   └── COMPATIBILITY.md
│
├── crates/
│   ├── body-finder-core/
│   ├── body-finder-protocol/
│   ├── body-finder-capabilities/
│   ├── body-finder-network/
│   ├── body-finder-timesync/
│   ├── body-finder-geometry/
│   ├── body-finder-radio/
│   ├── body-finder-rti/
│   ├── body-finder-fusion/
│   ├── body-finder-tracking/
│   ├── body-finder-uncertainty/
│   ├── body-finder-recording/
│   └── body-finder-ruview-adapter/
│
├── apps/
│   ├── mobile/
│   │   ├── android/
│   │   ├── ios/
│   │   └── src/
│   └── linux/
│
├── native/
│   ├── android-capabilities/
│   ├── ios-capabilities/
│   └── linux-capabilities/
│
├── firmware/
│   └── optional-ruview-esp32/
│
├── models/
│   ├── manifest.json
│   └── README.md
│
├── protocol/
│   ├── schemas/
│   └── fixtures/
│
├── validation/
│   ├── scenarios/
│   ├── fixtures/
│   ├── ground-truth/
│   ├── analysis/
│   └── reports/
│
├── scripts/
│   ├── bootstrap/
│   ├── lab/
│   ├── build/
│   └── release/
│
├── docs/
│   ├── architecture/
│   ├── adr/
│   ├── RUVIEW_TRUTH_MATRIX.md
│   ├── CAPABILITY_MATRIX.md
│   ├── VALIDATION_PROTOCOL.md
│   └── RELEASE_CRITERIA.md
│
└── .github/
    └── workflows/
```

---

# 7. Core domain contracts

## 7.1 Device descriptor

Every node advertises a runtime descriptor similar to:

```rust
pub struct DeviceDescriptor {
    pub node_id: NodeId,
    pub session_id: SessionId,
    pub platform: Platform,
    pub os_version: String,
    pub app_version: String,
    pub roles: Vec<NodeRole>,
    pub capabilities: CapabilitySet,
    pub battery_percent: Option<f32>,
    pub thermal_state: Option<ThermalState>,
    pub compute_score: f32,
    pub network_score: f32,
    pub sensing_score: f32,
}
```

Possible roles:

```text
DISPLAY
COORDINATOR
COMPUTE
RSSI_SENSOR
RTT_SENSOR
BLE_SENSOR
IMU_SENSOR
CSI_SENSOR
RECORDER
```

## 7.2 Capability result

Capabilities are not booleans derived from model names. They have probe state:

```text
UNKNOWN
API_PRESENT
PERMISSION_REQUIRED
PROBE_FAILED
WORKING
WORKING_DEGRADED
UNSUPPORTED
```

Example:

```json
{
  "wifi_rtt": {
    "state": "WORKING",
    "last_probe_ms": 1770000000000,
    "sample_count": 14,
    "median_sigma_m": 0.82
  }
}
```

## 7.3 Evidence frame

All sensing modalities convert to versioned normalized evidence:

```rust
pub struct EvidenceFrame {
    pub protocol_version: u16,
    pub node_id: NodeId,
    pub monotonic_ns: u64,
    pub synchronized_time_ns: i128,
    pub source: EvidenceSource,
    pub quality: f32,
    pub payload: EvidencePayload,
}
```

Sources include:

```text
WIFI_RSSI
WIFI_RTT
BLE_RSSI
IMU
CSI
RUVIEW_PRESENCE
RUVIEW_VITALS
RUVIEW_MAT
VISUAL_GEOMETRY
```

## 7.4 Human target

```rust
pub struct HumanTrack {
    pub id: TrackId,
    pub state: TrackState,
    pub position_m: [f64; 3],
    pub covariance_3x3: [[f64; 3]; 3],
    pub range_m: f64,
    pub bearing_deg: f64,
    pub depth_m: Option<f64>,
    pub existence_probability: f32,
    pub uncertainty_percent: f32,
    pub error_radius_95_m: f32,
    pub evidence_quality: EvidenceQuality,
    pub movement: Option<MovementEvidence>,
    pub breathing: Option<VitalEvidence>,
    pub heartbeat: Option<VitalEvidence>,
    pub provenance: Vec<EvidenceContribution>,
    pub updated_at_ns: i128,
}
```

---

# 8. Platform capability strategy

## 8.1 Android

Do not use device-name branches such as `if Pixel 7`. Use functional probes.

Probe:

- OS/API level.
- Wi-Fi state and permissions.
- current link metrics.
- nearby Wi-Fi scan capability and actual scan result availability.
- Wi-Fi RTT service presence and a real ranging attempt when peers/APs permit.
- Wi-Fi Aware / peer capability where available.
- Local-Only Hotspot.
- BLE scan/advertise/connect.
- accelerometer/gyro/magnetometer.
- camera/AR capability for optional geometry calibration.
- UWB only through an implemented, working platform adapter; API presence alone is insufficient.
- vendor/root CSI plugins only in Expert/advanced mode.

Android Wi-Fi RTT must be optional: not all Android devices support it.

### Android compatibility rule

“Any Android model” means:

> **No model whitelist and no assumed radio feature. The application runs on every Android device supported by the selected runtime and gracefully reduces features according to probes.**

At the reviewed Expo SDK 55 baseline, Expo documents Android 7+ support. Phase 0 must query the actual OS version of the Lenovo Tab2.

If the Lenovo Tab2 is below the chosen React Native/Expo minimum but still operationally valuable, create a **legacy node agent** rather than forcing the main UI to an obsolete framework:

```text
apps/android-legacy-agent/
```

The legacy agent only needs:

- node discovery,
- RSSI/BLE measurement where available,
- timestamps,
- protocol participation,
- status screen.

It does not need the full 3D UI.

## 8.2 iOS/iPadOS

The iOS app must remain valuable even though Apple limits general Wi-Fi scanning.

Probe/use:

- BLE,
- Core Motion / IMU,
- local-network connectivity,
- Bonjour discovery,
- hotspot network joining through supported NetworkExtension APIs,
- optional ranging capabilities only when a functional adapter proves them,
- optional camera-assisted sensor geometry calibration.

Do not claim iOS CSI or general Wi-Fi scanning without a verified API/entitlement/hardware path.

## 8.3 Native Ubuntu

Probe:

```bash
uname -a
ip link
nmcli device
iw dev
lspci -nnk
lsusb
rfkill list
bluetoothctl show
```

Then probe:

- RSSI/link metrics through `nl80211`/`iw` and appropriate kernel interfaces,
- nearby BSS observations where permitted,
- BlueZ BLE,
- hotspot creation via NetworkManager,
- monitor mode where hardware/driver permits,
- CSI adapter plugins only when actual supported interfaces are found.

Ubuntu is expected to win coordinator election when it has stronger compute/network stability, but election is score-based, not hard-coded.

## 8.4 WSL/Windows

Initial roles:

```text
COMPUTE
DEVELOPMENT
OPTIONAL DISPLAY
```

Do not treat WSL as an RF sensor by default. Promote it only after a functional probe demonstrates radio access with sufficient timestamp and measurement quality.

---

# 9. Capability score and coordinator election

Compute a deterministic score from normalized metrics:

```text
coordinator_score =
    0.30 * compute_score
  + 0.20 * network_stability
  + 0.15 * battery_or_power_score
  + 0.15 * timing_quality
  + 0.10 * storage_score
  + 0.10 * sensing_connectivity_score
```

Weights are initial engineering defaults and must be configurable.

Tie-break deterministically with stable `node_id` ordering.

Coordinator state must be replicated periodically to at least one successor candidate:

```text
session metadata
node registry
clock model
sensor geometry
calibration ID
active human tracks
track covariance
recording cursor
```

Failover must not silently reset target IDs.

---

# 10. Offline networking and discovery

## 10.1 Control plane

Use:

- mDNS/Bonjour where supported,
- UDP broadcast/multicast discovery as fallback,
- WebSocket or QUIC/TCP control stream after discovery.

The first implementation should prefer operational simplicity over an exotic transport.

## 10.2 Measurement plane

Use separate message classes for:

- low-rate control/state,
- radio measurements,
- optional high-rate CSI.

For CSI, prefer the existing RuView-compatible binary framing when practical rather than serializing large I/Q arrays as JSON.

## 10.3 Open field network mode

Because rapid/open networking was selected:

- no QR pairing is required,
- nodes with the current session ID may request entry,
- coordinator displays new nodes immediately,
- unknown nodes are marked `UNVERIFIED NODE`,
- strict schemas and message size limits are mandatory,
- replay windows and sequence numbers are mandatory,
- malformed packets are dropped and counted,
- never claim confidentiality/authentication in this mode.

Add a future ADR for optional secure mode, but do not block v1 on it.

---

# 11. Time synchronization

Multi-device radio localization is useless if timestamps are incomparable.

Implement a Body Finder time-sync service using monotonic clocks and repeated offset/RTT estimation.

For every peer maintain:

```text
clock_offset_ns
clock_drift_ppm
network_rtt_ns
sync_sigma_ns
last_sync
```

Do not use wall-clock timestamps for fusion.

Requirements:

- monotonic timestamps at measurement acquisition,
- conversion to coordinator timeline,
- periodic resynchronization,
- reject frames whose sync uncertainty exceeds the modality-specific threshold,
- record raw and synchronized timestamps for replay.

---

# 12. Sensor geometry engine

Human position is only meaningful if the sensor geometry is known sufficiently well.

## 12.1 Automatic ranging cascade

Try, in order of measurement quality rather than brand:

```text
verified UWB / precise ranging
        ↓
Wi-Fi RTT / FTM
        ↓
other platform ranging
        ↓
optional visual geometry calibration
        ↓
BLE/Wi-Fi coarse range constraints
        ↓
operator-assisted placement
```

The exact ordering may be changed by measured variance.

## 12.2 Optional visual calibration

Camera use is optional only.

It may be used to establish sensor/device positions or relative transforms. It may **not** be counted as human-through-wall evidence.

Store provenance distinctly:

```text
VISUAL_GEOMETRY != HUMAN_DETECTION_EVIDENCE
```

## 12.3 Moving operator

The operator is allowed to move during scanning.

Fuse:

- IMU orientation,
- step/displacement estimates when reliable,
- repeated radio geometry constraints,
- optional visual-inertial odometry.

The app may prompt:

```text
MOVE ~2 m RIGHT TO IMPROVE POSITION ESTIMATE
```

only when the fusion engine predicts a meaningful reduction in uncertainty.

## 12.4 Coordinate frames

Maintain:

```text
SESSION_FRAME
SENSOR_ARRAY_FRAME
OPERATOR_FRAME
DEVICE_LOCAL_FRAME
OPTIONAL_WORLD/GPS_FRAME
```

The radar displays targets in `OPERATOR_FRAME` by default.

---

# 13. Common-device human localization path

This is the highest-risk and highest-value workstream.

The first real implementation must not begin with deep learning. Begin with a deterministic, inspectable baseline that produces uncertainty and can be evaluated on the physical lab.

## 13.1 Background calibration

During initial calibration collect synchronized measurements with no intentional person in the scan zone:

```text
RSSI by link/BSSID
RTT by measurable peer/AP pair
BLE RSSI by pair
noise/variance
packet timing
orientation
sensor geometry
```

Calculate per-link baselines and noise models.

Persist calibration as a versioned artifact.

## 13.2 Dynamic link features

For every radio link compute features such as:

```text
ΔRSSI from baseline
rolling variance
median absolute deviation
spectral energy bands
CUSUM/change-point score
temporal autocorrelation
RTT residual from baseline
packet-loss change
cross-link correlation
```

Reuse RuView commodity Wi-Fi signal processing only after tests demonstrate compatible semantics.

## 13.3 Radio-tomographic occupancy grid

Create a 2D first implementation; extend to 3D only after 2D is validated.

Pipeline:

```text
synchronized link deltas
        ↓
link geometry / Fresnel-style weights
        ↓
regularized inverse problem
        ↓
occupancy likelihood grid
        ↓
spatial smoothing constrained by measured noise
        ↓
peak / connected-component hypotheses
        ↓
HumanObservation(s)
```

Candidate deterministic solvers:

- Tikhonov regularization,
- total-variation regularization,
- sparse Bayesian reconstruction.

Implement one baseline first and benchmark alternatives against recorded ground truth.

## 13.4 RTT disturbance path

Wi-Fi RTT is normally a **device/AP ranging** primitive, not automatically a body locator. However, synchronized RTT changes may provide device-free environmental evidence.

Treat this as an experimental Body Finder modality:

```text
baseline RTT distributions
        ↓
human-induced residual/anomaly features
        ↓
link likelihood contribution
        ↓
radio-tomographic fusion
```

Do not claim that ordinary RTT directly returns the human distance.

## 13.5 BLE path

BLE RSSI provides coarse, noisy constraints.

Use it primarily for:

- device topology,
- proximity ordering,
- geometry fallback,
- additional environmental-change evidence if validated.

It must carry lower default weight than a well-calibrated CSI or precise-ranging observation.

## 13.6 Multi-modal evidence fusion

Every modality outputs:

```text
likelihood field or observation
measurement covariance
quality score
source/provenance
```

Fusion must be uncertainty-weighted.

Never average positions from heterogeneous sensors without using their uncertainty.

---

# 14. CSI-enhanced RuView path

When `CSI_SENSOR=WORKING`, add the RuView path dynamically:

```text
raw CSI
  ↓
body-finder-ruview-adapter
  ↓
wifi-densepose-hardware
  ↓
wifi-densepose-signal
  ↓
validated RuView presence/motion/vitals components
  ↓
WiFi-Mat-compatible observations
  ↓
Body Finder fusion engine
```

CSI is an additional evidence source; it does not bypass Body Finder's uncertainty/provenance layer.

## 14.1 Feature gates

Examples:

```text
BODY_FINDER_RUVIEW_CSI
BODY_FINDER_RUVIEW_VITALS
BODY_FINDER_RUVIEW_MAT
BODY_FINDER_VENDOR_CSI_ANDROID
```

A gate becomes active only after:

1. compile-time compatibility,
2. unit/integration tests,
3. live functional probe when physical hardware is involved.

## 14.2 Optional ESP32 artifacts

The release pipeline may build upstream-compatible ESP32-S3/C6 firmware as optional artifacts because the overall release-artifact decision included firmware support.

However:

- they are not required for Body Finder startup,
- they are not part of the current validation laboratory,
- v1 common-device functionality must not silently depend on them.

Mark release artifacts clearly as `OPTIONAL CSI SENSOR FIRMWARE`.

---

# 15. Multi-target tracking

## 15.1 Observation-to-track lifecycle

```text
raw evidence
   ↓
spatial hypothesis
   ↓
POSSIBLE HUMAN
   ↓ temporal / cross-link confirmation
PROBABLE HUMAN
   ↓ stronger persistence / modality agreement
CONFIRMED TRACK
```

## 15.2 Tracking algorithm

Start with an uncertainty-aware state estimator:

```text
state = [x, y, z, vx, vy, vz]
```

Use:

- Kalman/EKF where the posterior is close to Gaussian,
- particle filter for ambiguous/multimodal RF likelihoods,
- clustering/mixture hypotheses before forcing target identity.

Do not prematurely implement complex neural tracking.

## 15.3 Lost targets

Targets do not disappear on a single missed observation.

Decay:

- existence probability,
- evidence quality,
- position precision.

Grow covariance with time.

Show `LOST / PREDICTED` until expiry or reacquisition.

---

# 16. Confidence and uncertainty

These must be separate concepts.

## 16.1 Human confidence

`human_confidence` estimates the probability that the fused evidence represents a human-related target rather than noise/environmental change.

It must be empirically calibrated from labelled tests. Do not expose an arbitrary neural-network score as a calibrated probability.

## 16.2 Position uncertainty

Primary metric:

```text
error_radius_95_m
```

For anisotropic uncertainty show an ellipse/ellipsoid derived from covariance rather than only a circle.

Percentage metric, initial definition:

```text
reference_scale_m = max(target_range_m, 2.0)
uncertainty_percent = clamp(100 * error_radius_95_m / reference_scale_m, 0, 100)
```

This percentage is for operator readability. **Meters remain the primary physical uncertainty metric.**

During validation, compare predicted 95% regions with real containment frequency. If a nominal 95% ellipse does not contain ground truth approximately 95% of the time across the validation set, recalibrate the covariance/uncertainty model.

## 16.3 Visualization

Radar rendering:

```text
            Target #1
             ●
          (     )      <- 95% uncertainty region
       (           )

          Operator ▲
```

As uncertainty rises, the region grows. Never keep a tiny target marker with only a small textual warning.

---

# 17. Vital signs priority

Position is the primary goal.

UI order:

1. position/direction/depth,
2. confidence + uncertainty,
3. movement,
4. breathing,
5. heartbeat.

Only show breathing/heartbeat when the currently active sensing path has validated support.

For common RSSI-only operation, it is acceptable for the vitals panel to say:

```text
BREATHING: unavailable with current sensing capabilities
HEARTBEAT: unavailable with current sensing capabilities
```

This is preferable to synthetic or inferred values.

---

# 18. Mobile application

## 18.1 Stack

- React Native + Expo modules for the shared UI/runtime.
- Custom native builds; Expo Go compatibility is **not** a requirement.
- Kotlin native modules for Android RF/network/sensor features.
- Swift native modules for iOS RF/network/sensor features.
- Rust shared core exposed through a stable FFI boundary where practical.

## 18.2 Screens

### Search / Radar — default

Show:

- operator at center,
- sensor nodes,
- possible/probable/confirmed humans,
- uncertainty rings/ellipses,
- distance and bearing,
- capability quality indicator,
- scan/calibration state.

### Map 2D

Show:

- sensor geometry,
- occupancy likelihood heatmap,
- walls/material hints when configured,
- target tracks and uncertainty.

### 3D

Show:

- x/y/z relative position,
- approximate depth,
- uncertainty volume,
- sensor nodes.

Do not show a detailed body pose unless the active sensing path truly produces and validates it.

### Targets

Per-target details and provenance.

### Devices

Operator-simple view:

```text
5 devices
Sensing quality: MEDIUM
Geometry: GOOD
Offline network: ACTIVE
```

Expert view:

```text
Pixel 10 Pro: RTT WORKING, BLE WORKING, IMU WORKING, CSI UNSUPPORTED
Pixel 7 Pro:  RTT WORKING, BLE WORKING, IMU WORKING, CSI UNSUPPORTED
Ubuntu:       RSSI WORKING, BLE WORKING, CSI PROBE_FAILED
...
```

### Recording / Ground Truth

Controls for experiments and replay.

### Settings

- EN / ES,
- Operator / Expert,
- open-network warning,
- recording controls,
- optional visual calibration,
- experimental feature flags.

## 18.3 Internationalization

Architect for English + Spanish from the beginning.

No hard-coded user-visible strings outside translation catalogs.

---

# 19. Linux application

Use:

- Rust for the daemon/core,
- Tauri for desktop shell if it remains the smallest reliable packaging path,
- shared web/React UI where practical,
- native Linux capability service for Wi-Fi/BLE/network interfaces.

The Linux process may act simultaneously as:

```text
COORDINATOR
COMPUTE
RECORDER
RSSI_SENSOR
BLE_SENSOR
CSI_SENSOR (only if proven)
DISPLAY
```

---

# 20. Recording and replay

Every real sensing bug must be reproducible without physically recreating the scene.

## 20.1 Session bundle

Define a `.bfsession` directory/archive:

```text
session.json
nodes.json
capabilities.json
geometry.json
calibration.json
measurements/
  wifi-rssi.bin
  wifi-rtt.bin
  ble.bin
  imu.bin
  csi.bin            # only if present
tracks.jsonl
ground_truth.json    # optional
logs/
manifest.sha256
```

## 20.2 Raw data

Raw RF/CSI storage is allowed locally.

Requirements:

- explicit recording indicator,
- bounded storage/rotation,
- no automatic cloud upload,
- platform-keystore-backed encryption at rest where implemented,
- document when raw platform data cannot be encrypted without unacceptable performance impact,
- hashes for integrity/reproducibility.

## 20.3 Deterministic replay

Command:

```bash
body-finder replay path/to/test.bfsession --deterministic
```

Replay should reproduce track outputs within defined numeric tolerances.

This is a mandatory CI regression tool.

---

# 21. Ground-truth and validation framework

## 21.1 Ground-truth record

For each labelled test record:

```text
true person position
sensor positions
operator position
wall/debris material
material thickness
number of persons
stationary/moving state
device topology
active capability path
RF measurements
predicted position
predicted covariance
predicted human confidence
actual localization error
```

## 21.2 Metrics

Generate automatically:

### Detection

- precision,
- recall,
- F1,
- false positives per minute,
- missed-target rate.

### Localization

- MAE,
- RMSE,
- median error,
- p90 error,
- p95 error,
- error by distance,
- error by material,
- error by topology,
- percentage achieving GOLD/GOOD/USABLE/COARSE.

### Uncertainty calibration

- empirical coverage of 50/80/90/95% predicted regions,
- calibration error,
- confidence reliability diagram.

### Tracking

- track continuity,
- ID switches,
- reacquisition time.

## 21.3 Reduced mandatory v1 validation matrix

A reduced matrix was chosen for development speed. These scenarios are still mandatory:

1. **Empty scene** — establish false-positive behavior.
2. **One person LOS** — near / medium / far positions.
3. **One stationary person** — test low-motion evidence.
4. **One moving person**.
5. **One person through one representative wall** at multiple known positions.
6. **Two persons**, at least one scenario, to test track separation/cluster behavior.
7. **Offline network** with no Internet.
8. **Node added during scan**.
9. **Node removed during scan**.
10. **Coordinator failover**.
11. **Common-device-only configuration** using the available Android + native Ubuntu lab.
12. **Safe rubble proxy fixture** using material between sensors and a person; never put a person in an unstable structure.

Add additional materials/distances before making broad marketing claims.

---

# 22. Safe rubble fixture

Because no real rubble environment is currently required, construct a controlled fixture.

Examples of safe intervening materials:

- brick/block stack,
- wood panels,
- drywall,
- concrete blocks where safely supported,
- mixed loose non-structural material in a stable frame.

Record:

- thickness,
- approximate composition,
- geometry,
- sensor distance,
- person position.

Never ask a test subject to enter a collapse hazard.

---

# 23. Release artifacts

Each successful `dev-N` release should publish as many of the following as the current phase supports.

## 23.1 Android

```text
body-finder-ruview-universal.apk
body-finder-ruview-arm64-v8a.apk
body-finder-ruview-armeabi-v7a.apk       # if runtime supports
body-finder-ruview-x86_64.apk            # emulator/dev as appropriate
body-finder-ruview.aab
```

The universal APK is the primary sideload artifact.

Do not make RTT/CSI a manifest `required` feature. Optional RF features must remain runtime-detected so the APK installs on devices that do not provide them.

## 23.2 iOS

Current constraint: there is **no paid Apple Developer Program account**.

Therefore CI must initially produce:

```text
body-finder-ruview-ios-simulator.tar.gz
build logs
symbol/debug artifacts where useful
```

A generally installable physical-device IPA cannot be distributed from GitHub without appropriate Apple signing/provisioning.

Prepare the pipeline so that, once signing credentials are configured, it automatically adds:

```text
body-finder-ruview.ipa
```

through an appropriate signed distribution profile.

Do not represent an unsigned simulator build as an installable physical iPhone package.

## 23.3 Ubuntu

```text
body-finder-ruview-linux-x86_64.deb
body-finder-ruview-linux-x86_64.AppImage
body-finder-ruview-linux-x86_64.tar.gz

body-finder-ruview-linux-arm64.deb
body-finder-ruview-linux-arm64.AppImage   # where build tooling supports it reliably
body-finder-ruview-linux-arm64.tar.gz
```

## 23.4 Containers

```text
linux/amd64 Docker image
linux/arm64 Docker image
```

Container is primarily for compute/coordinator/server deployments; hardware passthrough must be documented separately.

## 23.5 Optional firmware

```text
ruview-optional-esp32-s3.bin
ruview-optional-esp32-c6.bin
```

Only if the upstream-compatible firmware build is reproducible and license-compatible.

## 23.6 Release metadata

Every release includes:

```text
SHA256SUMS
SBOM.spdx.json
release-manifest.json
THIRD_PARTY_LICENSES.txt
CHANGELOG.md excerpt
protocol-version.txt
ruview-upstream-lock.json
model-manifest.json
```

---

# 24. CI/CD architecture

## 24.1 PR gates

Mandatory:

```text
Rust format
Rust clippy
Rust unit tests
Rust integration tests
TypeScript lint
TypeScript typecheck
mobile unit tests
protocol compatibility tests
deterministic replay tests
Android compile
Linux x86_64 compile
security/dependency scan
SBOM generation smoke test
```

Add Linux arm64 and iOS simulator build as soon as their project scaffolds exist.

## 24.2 Release gate

A `dev-N` prerelease must not publish if any applicable mandatory gate fails.

Exception handling must be explicit; do not silently mark a failed platform as optional after it has entered the release matrix.

## 24.3 Workflow model

```text
feature/*
   ↓
PR
   ↓ mandatory CI
main
   ↓
automatic dev-N prerelease
   ↓
validated milestone
   ↓
v0.x
   ↓
physical through-wall validation + release criteria
   ↓
v1.0
```

## 24.4 Upstream compatibility workflow

Scheduled/manual workflow:

```text
check latest RuView commit
        ↓
create temporary compatibility branch
        ↓
update pin
        ↓
build relevant crates
        ↓
run adapter contract tests
        ↓
run deterministic replays
        ↓
report diff
```

It must **not** auto-merge an upstream update into production.

---

# 25. Development phases

Each phase should normally be one or a small number of PRs. Codex must not bury multiple architectural changes inside a giant PR.

---

## Phase 0 — Baseline, upstream truth audit, and lab inventory

### Goal

Establish what actually builds and what the available hardware can actually do.

### Tasks

1. Add repository baseline files.
2. Pin current RuView revision.
3. Reproduce relevant RuView Rust crate builds/tests.
4. Reproduce RuView mobile build.
5. Resolve Expo/RN dependency mismatch without adding Body Finder features.
6. Build `RUVIEW_TRUTH_MATRIX.md`.
7. Create capability-probe scripts for lab devices.
8. Query all three Android devices through ADB where possible:
   ```bash
   adb shell getprop
   adb shell pm list features
   adb shell dumpsys wifi
   adb shell dumpsys bluetooth_manager
   adb shell dumpsys sensorservice
   ```
9. Detect exact Lenovo Tab2 model/Android version.
10. Inventory native Ubuntu Wi-Fi/BLE adapters and drivers.
11. Record WSL limitations separately.
12. Create `docs/CAPABILITY_MATRIX.md`.

### Required outputs

```text
upstream/ruvieW.lock.json
docs/RUVIEW_TRUTH_MATRIX.md
docs/CAPABILITY_MATRIX.md
validation/reports/phase0-lab-inventory.md
```

### Acceptance criteria

- Relevant upstream Rust components compile or failures are documented with reproducible commands.
- Mobile baseline has a pinned buildable dependency graph.
- Pixel 7 Pro, Pixel 10 Pro, Lenovo Tab2, Ubuntu native, and WSL node appear in the capability report.
- No capability is marked WORKING without a functional probe.

### Stop condition

Do not begin sensing implementation while the mobile baseline or Rust adapter baseline is unreproducible.

---

## Phase 1 — Monorepo, protocol, shared Rust core

### Goal

Create stable contracts before platform-specific sensing.

### Tasks

- Rust workspace.
- protocol crate.
- device/capability domain.
- evidence frame.
- human track domain.
- covariance/uncertainty primitives.
- versioned protocol fixtures.
- TypeScript bindings/types.

### Tests

- serialization round-trips,
- malformed packet rejection,
- version compatibility,
- covariance math,
- uncertainty percentage boundaries.

### Acceptance

Linux CLI can generate and consume protocol fixtures; TypeScript can parse the same fixtures.

---

## Phase 2 — Mobile/Linux shells and unified UI baseline

### Goal

Install the same product identity across Android/iOS/Linux.

### Tasks

- create `apps/mobile`,
- Operator/Expert mode shell,
- EN/ES infrastructure,
- create `apps/linux`,
- shared design tokens,
- connection/device store,
- radar placeholder driven only by deterministic fixtures.

### Acceptance

- Android APK installs on supported lab Android devices.
- Linux app launches natively on Ubuntu.
- iOS simulator build succeeds on CI once runner/toolchain is configured.
- Radar fixture clearly displays uncertainty region.

---

## Phase 3 — Functional capability discovery

### Goal

Automatically discover what each device can contribute.

### Android

Implement Kotlin module probes for:

- Wi-Fi/link,
- scanning,
- RTT,
- hotspot,
- BLE,
- IMU,
- camera calibration availability.

### iOS

Implement Swift probes for:

- BLE,
- motion,
- local networking/Bonjour,
- supported hotspot-join path,
- optional ranging adapters.

### Linux

Implement Rust probes for:

- NetworkManager,
- nl80211/iw,
- RSSI,
- BLE/BlueZ,
- hotspot,
- optional CSI plugin discovery.

### Acceptance

Opening Devices/Expert mode shows real probe results, not hard-coded values.

---

## Phase 4 — Offline sensor fabric and coordinator failover

### Goal

All lab nodes discover each other without Internet.

### Tasks

- LAN discovery,
- Ubuntu hotspot fallback,
- Android Local-Only Hotspot fallback,
- node registry,
- coordinator score,
- deterministic election,
- replicated minimal session state,
- add/remove node hot-plug,
- failover.

### Acceptance test

1. Disable Internet.
2. Start native Ubuntu + at least two Android devices.
3. All nodes appear automatically.
4. Kill coordinator.
5. New coordinator elected.
6. Session ID and existing fixture track survive.

---

## Phase 5 — Time sync and sensor geometry

### Goal

Know where sensors are and align their measurements.

### Tasks

- monotonic time synchronization,
- RTT geometry adapter,
- BLE coarse geometry fallback,
- IMU pose/orientation,
- optional visual geometry calibration,
- graph solver,
- geometry covariance.

### Acceptance

In a labelled lab layout, the UI shows sensor relative positions and each sensor's geometry uncertainty.

---

## Phase 6 — Real commodity RF collection

### Goal

Replace all radio fixtures with recorded real measurements.

### Tasks

- Android measurement stream,
- Linux measurement stream,
- iOS available measurement stream,
- normalized evidence frames,
- recording,
- empty-room calibration,
- deterministic replay.

### Acceptance

Record `.bfsession` from the physical lab and replay it offline with the same normalized evidence sequence.

---

## Phase 7 — Deterministic device-free localization baseline

### Goal

Produce the first real human-position likelihood map using ordinary-device radio measurements.

### Tasks

1. background subtraction,
2. per-link noise modelling,
3. synchronized link feature vectors,
4. geometric weight matrix,
5. 2D regularized inverse solver,
6. occupancy probability/score grid,
7. target hypothesis extraction,
8. position covariance,
9. radar display.

### Acceptance

With known ground truth in LOS tests, the system produces:

- a target hypothesis,
- relative x/y,
- error region,
- actual recorded localization error.

Do not optimize deep learning before this baseline exists.

---

## Phase 8 — Tracking and multi-target fusion

### Goal

Turn frame-level peaks into stable targets.

### Tasks

- track lifecycle,
- temporal filtering,
- covariance propagation,
- cluster state,
- lost/reacquired,
- node-weight changes,
- provenance.

### Acceptance

One moving target remains the same track across the lab; two unresolved persons produce a cluster rather than fake precision.

---

## Phase 9 — RuView / CSI enhanced adapter

### Goal

Integrate real RuView sensing when a real CSI path is available, without making it mandatory.

### Tasks

- adapter contracts,
- feature flags,
- CSI frame normalization,
- RuView signal processing integration,
- validated presence/motion outputs,
- vitals only after physical validation,
- WiFi-Mat observation mapping,
- provenance in fusion.

### Acceptance

A recorded or physical real-CSI fixture passes through the adapter without any simulated fallback being mislabeled as live.

If no CSI-capable common device is present in the current lab, the phase may validate against upstream real captured data and remain `UNVALIDATED_ON_LOCAL_PHYSICAL_HARDWARE`; it must not block common-device development.

---

## Phase 10 — Through-wall and safe-rubble validation

### Goal

Determine empirically whether the common-device system can satisfy the central product claim.

### Procedure

- establish known sensor geometry,
- establish empty baseline,
- place one person at known coordinates behind a stable representative wall,
- record repeated trials,
- repeat at multiple positions,
- run one safe rubble-proxy fixture,
- compare predicted vs true location,
- generate automatic report.

### Required output

```text
validation/reports/through-wall-<version>.md
validation/reports/through-wall-<version>.json
```

### Acceptance classes

Report the actual achieved tier:

```text
GOLD / GOOD / USABLE / COARSE / PRESENCE-ONLY / FAILED
```

### Critical release rule

If Body Finder cannot repeatedly localize the through-wall person better than the agreed product acceptance threshold, **do not call the build v1.0 and do not claim validated through-wall localization.** Continue as `v0.x` with the measured capability documented.

---

## Phase 11 — Packaging and automated dev releases

### Goal

Every merged milestone produces installable artifacts automatically.

### Tasks

- Android universal APK,
- ABI APKs where practical,
- AAB,
- Linux deb/AppImage/tar,
- Docker multi-arch,
- iOS simulator artifact,
- prepared signed-IPA job disabled until credentials exist,
- optional ESP32 firmware builds,
- SBOM,
- SHA256SUMS,
- release manifest,
- provenance/upstream lock.

### Acceptance

A clean GitHub-hosted CI run can create the release without relying on the developer laptop.

---

## Phase 12 — v1.0 release gate

### Required gates

- common-device application installs and runs on supported lab devices,
- no model whitelist,
- offline sensor fabric works,
- auto capability selection works,
- node hot-add/remove works,
- coordinator failover works,
- real recorded radio data used,
- ground-truth localization metrics generated,
- uncertainty calibration measured,
- through-wall validation passes the declared acceptance class,
- false-positive empty-scene test documented,
- target provenance exposed,
- deterministic replay passes,
- all applicable CI tests green,
- Android and Ubuntu installable artifacts published,
- iOS simulator artifact published and physical IPA limitation clearly documented until signing credentials exist,
- SBOM/checksums/license notices published.

Only then tag:

```text
v1.0.0
```

---

# 26. Codex execution protocol

Codex should treat this document as the project contract.

## 26.1 At the start of every phase

1. Read this plan.
2. Read current `docs/adr/` decisions.
3. Inspect current repository state; never assume a previous phase is complete just because the plan says it should be.
4. Run relevant existing tests before changes.
5. Create a phase/feature branch.
6. Keep the PR focused.

## 26.2 Before every PR

Codex must provide in the PR body:

```text
Goal
Architecture impact
Files changed
Tests added
Commands executed
Physical devices used, if any
Simulation/fixture/live-data classification
Known limitations
Acceptance criteria status
```

## 26.3 No fake completion

Codex must not mark a phase complete when:

- a test is skipped without reason,
- a sensing input is simulated but the phase requires live data,
- a feature is hard-coded to make UI tests pass,
- a target position is generated from a fixture in a physical validation phase,
- an upstream claim is copied without local evidence,
- CI is red.

## 26.4 Physical-test stop conditions

When a phase requires actual phones/Ubuntu hardware and CI cannot perform the test automatically:

- build and publish the `dev-N` artifact,
- provide the exact minimal test steps,
- collect logs/recording from the user's run,
- run automated analysis on the returned `.bfsession`,
- only then close the physical acceptance criterion.

---

# 27. Initial lab test topology

Preferred first topology:

```text
                  Native Ubuntu
             coordinator candidate
                Wi-Fi / BLE / RF
                 /      |      \
                /       |       \
       Pixel 10 Pro  Pixel 7 Pro  Lenovo Tab2
          node A        node B       node C
```

The first goal is **not** through-wall localization.

Progression:

```text
A. all nodes discover
B. capability matrix is real
C. clocks synchronize
D. device geometry is estimated
E. real RF data records
F. empty/person changes are measurable
G. LOS position likelihood appears
H. LOS error is measured
I. through-wall trial
J. safe rubble proxy
```

Do not skip from A directly to I.

---

# 28. Risk register

## R1 — Ordinary phones may not expose enough RF information for useful through-wall localization

**Probability:** high  
**Impact:** critical

Mitigation:

- multi-node fusion,
- RTT where available,
- RSSI tomography,
- guided operator movement,
- Ubuntu radio capabilities,
- optional CSI plugin architecture,
- strict validation before v1 claim.

This risk cannot be solved by software promises.

## R2 — Android fragmentation

Mitigation:

- functional probes,
- no model whitelist,
- optional feature flags,
- legacy lightweight node agent if an important older device falls below the main UI runtime minimum.

## R3 — iOS Wi-Fi restrictions

Mitigation:

- treat iOS as UI/compute/BLE/IMU/network participant by default,
- never make generalized Wi-Fi scan/CSI a requirement,
- conditionally enable only verified entitlements/APIs.

## R4 — Poor sensor geometry

Mitigation:

- geometry uncertainty,
- RTT when available,
- optional camera calibration,
- guided operator movement,
- never hide geometry quality.

## R5 — Open local network can be spoofed

Mitigation:

- explicit warning,
- strict parsing,
- replay protection,
- session IDs,
- optional secure mode later.

Do not claim network authenticity in open mode.

## R6 — Upstream RuView changes rapidly

Mitigation:

- exact commit pin,
- adapter layer,
- compatibility CI,
- manual promotion of upstream updates.

## R7 — Synthetic/demo code contaminates real sensing

Mitigation:

- data-source type embedded in every evidence frame,
- CI rule preventing `SIMULATED` evidence from satisfying physical gates,
- prominent `SIM` mode indicator wherever simulation exists.

## R8 — Confidence is not calibrated

Mitigation:

- ground-truth dataset,
- reliability diagrams,
- covariance coverage checks,
- versioned calibration parameters.

## R9 — iOS physical artifact cannot currently be distributed

Cause: no Apple Developer Program credentials.

Mitigation:

- simulator build now,
- keep signed IPA workflow ready,
- activate when signing credentials exist.

---

# 29. Definition of Done for the product vision

The project is successful when a fresh user can:

1. download the appropriate release artifact,
2. install Body Finder – RuView on common supported devices,
3. turn off Internet,
4. open the app on multiple devices,
5. have devices automatically discover one another,
6. see the automatically detected capabilities,
7. begin calibration,
8. start scanning,
9. receive one or more possible-human tracks derived from real RF measurements,
10. see the best available relative position of every track on radar,
11. see distance, direction, depth when supportable, confidence, uncertainty percentage, and ±meters,
12. inspect which nodes/modalities contributed,
13. add/remove a device without restarting,
14. survive coordinator failure,
15. record/replay the session,
16. obtain measured validation reports rather than inherited upstream claims,
17. install published Android/Ubuntu release packages directly,
18. obtain iOS simulator artifacts immediately and a signed physical IPA automatically once Apple signing is configured.

For the specific through-wall product claim, success additionally requires repeated controlled tests showing that the system localizes a human behind the tested wall/rubble proxy at the quality tier declared in the release notes.

---

# 30. First Codex work order

Start only with **Phase 0**.

Suggested Codex prompt:

```text
Read IMPLEMENTATION_PLAN.md completely.

Execute Phase 0 only.
Do not implement the final sensing/localization algorithm yet.

Goals:
1. Pin and audit the current RuView upstream revision.
2. Reproduce the relevant Rust crates and mobile app builds.
3. Resolve/pin a reproducible mobile dependency set without mixing in product features.
4. Build docs/RUVIEW_TRUTH_MATRIX.md.
5. Build scripts that functionally probe Android, native Ubuntu, and WSL capabilities.
6. Produce docs/CAPABILITY_MATRIX.md and validation/reports/phase0-lab-inventory.md.
7. Add tests and CI for everything introduced.

Important constraints:
- Never infer RF capabilities from the phone model alone.
- Never label RSSI as CSI.
- Never use simulated data to satisfy a physical capability probe.
- Keep RuView behind a compatibility boundary.
- Do not add ESP32 as a dependency.
- Preserve Android compatibility through runtime feature detection rather than required hardware features.

Open a focused PR with exact commands/tests/results and stop at the Phase 0 acceptance criteria.
```

---

# 31. Primary technical references

## RuView

- Main repository: `https://github.com/ruvnet/RuView`
- WiFi-Mat guide: `https://github.com/ruvnet/RuView/blob/main/docs/wifi-mat-user-guide.md`
- WiFi-Mat crate: `v2/crates/wifi-densepose-mat`
- Hardware crate: `v2/crates/wifi-densepose-hardware`
- Commodity/multi-BSSID Wi-Fi crate: `v2/crates/wifi-densepose-wifiscan`
- Mobile app: `ui/mobile`
- Mobile architecture ADR: `docs/adr/ADR-034-expo-mobile-app.md`
- Build guide: `docs/build-guide.md`

## Android official references

- Wi-Fi RTT: `https://developer.android.com/develop/connectivity/wifi/wifi-rtt`
- `android.net.wifi.rtt`: `https://developer.android.com/reference/android/net/wifi/rtt/package-summary`
- `WifiManager.startLocalOnlyHotspot`: `https://developer.android.com/reference/android/net/wifi/WifiManager`

Important implementation facts to preserve:

- Wi-Fi RTT is optional and must be runtime-detected.
- RTT can measure distance to supporting APs/peer Wi-Fi Aware devices.
- Local-Only Hotspot creates a local Wi-Fi network without Internet access.

## Apple official references

- Wi-Fi configuration: `https://developer.apple.com/documentation/networkextension/wi-fi-configuration`
- `NEHotspotConfiguration`: `https://developer.apple.com/documentation/networkextension/nehotspotconfiguration`

Important implementation fact: joining/configuring Wi-Fi from iOS is permission/entitlement constrained; do not assume unrestricted scanning or CSI.

## Expo official references

- SDK compatibility: `https://docs.expo.dev/versions/v55.0.0/`
- Internal distribution: `https://docs.expo.dev/build/internal-distribution/`
- Android APK builds: `https://docs.expo.dev/build-reference/apk/`

---

# 32. Final release principle

The project should optimize aggressively for finding a human's position, but it must remain **evidence-driven**.

The release hierarchy is therefore:

```text
Does it install?                         → packaging gate
Can nodes find each other offline?       → fabric gate
Can they measure real RF?                → sensing gate
Can geometry be estimated?               → geometry gate
Can a human-related change be detected?  → detection gate
Can it be localized in LOS?              → localization gate
Can uncertainty predict actual error?    → calibration gate
Can it localize through the test wall?   → through-wall gate
Can the result survive repeated trials?  → v1.0 claim gate
```

**No later gate may be declared passed because an earlier gate passed.**

That rule is the central engineering safeguard for Body Finder – RuView.
