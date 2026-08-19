# Body Finder – RuView: Automatic Geometry + Test Release Implementation Plan

> Repository: `Trochez/body_finder-RuView_WiFi-Mat`  
> Date: 2026-08-16  
> Status: **LOCKED IMPLEMENTATION REQUIREMENTS**  
> Scope: mandatory automatic node geometry, inter-node ranging, UI changes, validation, logging, CI/release artifacts, and physical-test protocol.  
> Relationship to `IMPLEMENTATION_PLAN.md`: this document **extends and supersedes any conflicting requirement that asks an operator to enter node coordinates manually**. All non-conflicting requirements from the master plan remain in force.

---

## 0. Executive decision

The Body Finder operator must **never be required to type the physical X/Y/Z position of a sensing node during normal operation**.

The current experimental build asks the operator to enter node coordinates manually and uses those coordinates to estimate a target. That behavior is temporary and must be removed from the normal product flow.

The product must instead:

1. discover available nodes automatically;
2. functionally probe each node for real ranging capabilities;
3. collect real inter-node distance/angle constraints whenever the OS/hardware exposes them;
4. build a pairwise measurement graph;
5. solve a relative coordinate frame automatically;
6. continuously refine the geometry as measurements arrive;
7. expose geometry confidence/uncertainty and observability honestly;
8. refuse to fabricate coordinates when the measurement graph is insufficient;
9. use the solved geometry as an input to human-presence/localization fusion;
10. produce a complete `dev-*` prerelease containing the APK and all artifacts required to test this behavior on the available Android, Ubuntu, WSL and Windows devices.

The operator may measure real positions with a tape measure **only as external ground truth for validation**. Ground-truth coordinates must never be fed into the production geometry solver during an acceptance test.

---

# 1. Locked product requirements

## 1.1 Zero mandatory manual node coordinates

Normal UI and CLI flows must not contain required fields/options such as:

```text
x = ?
y = ?
z = ?
Set position
--x
--y
--z
```

for the purpose of making the application operational.

A developer-only ground-truth/debug override may exist, but it must satisfy **all** of the following:

- hidden under Expert/Developer mode;
- disabled by default;
- visibly marked `GROUND TRUTH / DEBUG ONLY`;
- excluded from automatic geometry acceptance metrics when enabled;
- persisted in logs as `manual_geometry_override=true`;
- never silently substituted when automatic geometry fails.

## 1.2 Relative geometry, not global GPS

Body Finder requires an internally consistent **relative local coordinate frame**. It does not need latitude/longitude or an absolute map origin.

Default coordinate gauge:

```text
Anchor node A = (0, 0, 0)
Anchor node B = (+dAB, 0, 0)
Remaining nodes = solved from measured constraints
```

The origin and orientation are arbitrary and may change after coordinator failover. What matters is that all sensor and target positions remain mutually consistent and that any frame transform is communicated atomically.

## 1.3 Node-count semantics

Node count alone is **not enough**. The solver must inspect graph connectivity and independent constraints.

Expected behavior:

- **1 node**: no array geometry; node is origin only.
- **2 nodes**: a 1D baseline may be established if a defensible distance constraint exists; no fake 2D solution.
- **3 nodes**: a 2D solution may be established only when enough valid non-degenerate pairwise constraints exist.
- **4+ nodes**: use redundant edges for robust refinement, outlier rejection, uncertainty reduction and failover.
- **3D**: enable only when vertical observability is actually present; otherwise explicitly remain 2D with `z=0` as a frame convention, not as a measured altitude.

Do not equate `nodes >= 3` with `geometry solved`.

## 1.4 Honest failure/degradation

If geometry cannot be solved, the UI must show a state such as:

```text
DISCOVERING NODES
RANGING
GEOMETRY INSUFFICIENT
GEOMETRY 1D
GEOMETRY 2D
GEOMETRY DEGRADED
GEOMETRY STALE
```

and explain the reason in Expert mode, for example:

```text
Only one valid pairwise distance edge
Graph disconnected
Nodes nearly collinear
Ranging technology unavailable
Ranging samples too unstable
Peer lost
Solver residual too large
```

Never invent a triangle, place nodes at fixed defaults, or silently reuse stale coordinates as if they were current.

---

# 2. Technology strategy for automatic ranging

The implementation must use a **capability cascade**. No Android model whitelist is allowed; every capability must be functionally probed at runtime.

## 2.1 Android API 36+ preferred path

On Android 16 / API 36+, first probe the platform Ranging API (`android.ranging.RangingManager`). When supported between the participating devices, prefer technologies in this approximate quality order:

1. UWB;
2. Bluetooth Channel Sounding;
3. Wi-Fi NAN / Wi-Fi Aware RTT;
4. Bluetooth RSSI ranging.

Do not assume all API-36 devices support all technologies. Query capabilities and availability, then establish a real session.

## 2.2 Android API 28–35 fallback

Probe and use `WifiRttManager` when available.

Valid range targets may include:

- RTT-capable Wi-Fi access points;
- Wi-Fi Aware peers that expose ranging.

For peer-to-peer phone geometry, Wi-Fi Aware discovery/ranging should be used where both nodes functionally support it.

RTT access-point measurements may also be useful as **shared anchors** when multiple nodes can range the same APs. AP coordinates must not be invented. Unknown AP positions can be jointly optimized as latent anchors if the graph is sufficiently constrained, or used only as relative constraints.

## 2.3 UWB optional adapter

Where supported, use a stable AndroidX UWB API version and treat UWB as a high-quality optional adapter.

UWB must never become a minimum device requirement.

## 2.4 BLE fallback

All compatible nodes should expose a Body Finder BLE identity/service suitable for peer discovery and ranging-related observations.

BLE RSSI-derived distance is allowed only as a **low-confidence measurement source** with a calibrated/learned uncertainty model. It must never be presented as precision ranging equivalent to UWB, Bluetooth Channel Sounding or RTT.

Required BLE safeguards:

- persistent Body Finder node identity separate from transient MAC/address representations;
- advertisement/service identity binding;
- per-peer RSSI sample windows;
- median/robust filtering;
- environment/model-specific sigma;
- NLOS/multipath quality penalties;
- no hard-coded claim that one RSSI value corresponds exactly to one distance.

## 2.5 Commodity Wi-Fi connected-link RSSI

The existing connected-Wi-Fi RSSI measurement may remain useful for human-presence experiments, but it **must not be treated as a direct inter-phone distance measurement** unless an explicitly validated calibration/model says so.

The automatic geometry subsystem therefore needs new pairwise-ranging measurements beyond the current single connected-link Wi-Fi RSSI field.

## 2.6 Ubuntu, Windows and WSL

Native Ubuntu and Windows nodes must functionally probe whatever ranging/radio sources are genuinely available.

- Native Ubuntu may contribute BLE peer RSSI, Wi-Fi radio information, optional supported ranging hardware, CSI where independently verified, compute and coordinator roles.
- Windows may contribute real available peer/radio measurements and compute/network roles.
- WSL must be treated primarily as compute/development unless direct RF access is proven at runtime.
- Lack of RF on WSL is a truthful capability result, not an error to conceal.

A node that cannot range peers can still participate as display/compute/coordinator if the graph can be solved by other nodes.

---

# 3. New protocol/domain contracts

Create explicit normalized contracts. Names may be adapted to project style, but semantics are mandatory.

## 3.1 Ranging capability descriptor

```rust
pub struct RangingCapability {
    pub technology: RangingTechnology,
    pub state: CapabilityState,
    pub max_peers: Option<u32>,
    pub supports_distance: bool,
    pub supports_azimuth: bool,
    pub supports_elevation: bool,
    pub detail: String,
}

pub enum RangingTechnology {
    AndroidRangingUwb,
    AndroidRangingBleCs,
    AndroidRangingWifiNanRtt,
    AndroidRangingBleRssi,
    WifiRttAware,
    WifiRttAccessPoint,
    AndroidxUwb,
    BleRssi,
    LinuxAdapter,
    WindowsAdapter,
    Unknown,
}
```

## 3.2 Pairwise range observation

```rust
pub struct PairwiseRangeObservation {
    pub session_id: SessionId,
    pub observer_node_id: NodeId,
    pub peer_node_id: NodeId,
    pub technology: RangingTechnology,
    pub monotonic_ns: u64,
    pub distance_m: Option<f64>,
    pub distance_sigma_m: Option<f64>,
    pub azimuth_deg: Option<f64>,
    pub azimuth_sigma_deg: Option<f64>,
    pub elevation_deg: Option<f64>,
    pub elevation_sigma_deg: Option<f64>,
    pub rssi_dbm: Option<f64>,
    pub quality: MeasurementQuality,
    pub source_detail: String,
}
```

Every observation must preserve provenance. No conversion may erase the original source.

## 3.3 Geometry graph

The coordinator/fusion layer maintains:

```text
nodes = sensor nodes
edges = normalized pairwise range/angle constraints
edge weights = inverse uncertainty × recency × quality
```

Requirements:

- reject cross-session data;
- reject replayed/out-of-order data outside tolerance;
- expire stale edges;
- keep short rolling histories per pair and technology;
- combine reciprocal measurements without double-counting correlated samples;
- expose connected components;
- expose graph observability/degeneracy.

## 3.4 Geometry solution

```rust
pub struct GeometrySolution {
    pub frame_id: String,
    pub revision: u64,
    pub generated_monotonic_ns: u64,
    pub dimension: GeometryDimension,
    pub state: GeometryState,
    pub anchor_node_id: NodeId,
    pub axis_node_id: Option<NodeId>,
    pub positions: Vec<NodePositionEstimate>,
    pub residual_rms_m: Option<f64>,
    pub condition_score: Option<f64>,
    pub used_edges: Vec<EdgeId>,
    pub rejected_edges: Vec<RejectedEdge>,
    pub reason: Option<String>,
}

pub struct NodePositionEstimate {
    pub node_id: NodeId,
    pub x_m: f64,
    pub y_m: f64,
    pub z_m: f64,
    pub covariance: Vec<f64>,
    pub error_radius_95_m: Option<f64>,
}
```

All consumers must be able to distinguish a solved coordinate from a default/unknown value.

---

# 4. Automatic geometry solver

## 4.1 Deterministic frame initialization

For a connected component with sufficient constraints:

1. choose the anchor deterministically from stable node properties/graph quality;
2. place anchor A at `(0,0,0)`;
3. choose axis node B with a high-quality range edge and good graph connectivity;
4. place B at `(+dAB,0,0)`;
5. choose a third node C that maximizes geometric leverage and is supported by enough independent constraints;
6. initialize C through trilateration/angle constraints;
7. resolve mirror ambiguity deterministically and keep the choice stable across small updates;
8. initialize remaining nodes from strongest available constraints;
9. optimize globally.

The solver must avoid coordinate flips on every update. If the gauge changes after failover, publish an explicit frame transform/revision.

## 4.2 Robust optimization

Use weighted nonlinear least squares or an equivalent robust graph optimizer.

Minimum requirements:

- weight by measurement sigma/quality;
- robust loss such as Huber/Cauchy to reduce outlier influence;
- reject physically impossible distances;
- detect persistent bad edges;
- avoid solving disconnected components as one array;
- compute residuals per edge;
- calculate an uncertainty approximation from the local Jacobian/Hessian or a documented statistically defensible alternative.

Do not use a simple centroid as the sensor geometry solver.

## 4.3 Degeneracy detection

Explicitly detect:

- fewer independent constraints than degrees of freedom;
- disconnected graph;
- nearly collinear 2D geometry;
- poor vertical observability in 3D;
- extremely ill-conditioned normal matrix;
- residuals inconsistent with reported sensor uncertainty.

If degenerate, lower the geometry state rather than forcing a position.

## 4.4 2D before 3D

The first acceptance target is stable automatic **2D sensor geometry**.

3D is enabled only after the 2D pipeline is working and a real measurement path contains vertical information sufficient to constrain Z. If not, continue to report `dimension=2D`.

## 4.5 Continuous refinement

Geometry is not a one-time startup step.

The solver must update when:

- a node joins;
- a node leaves;
- a better ranging technology becomes available;
- a peer changes position;
- measurements become stale;
- coordinator changes.

Use smoothing/hysteresis so measurement noise does not make nodes visually jump without bound.

---

# 5. Interaction with human localization

Sensor geometry and human localization are separate estimation layers.

Required order:

```text
peer discovery
    ↓
inter-node ranging
    ↓
automatic sensor geometry
    ↓
background calibration
    ↓
human-presence observations
    ↓
human fusion/localization
    ↓
relative target position + uncertainty
```

A target location must not be presented as defensible when sensor geometry is unknown or too uncertain for the selected localization method.

Human-target uncertainty must include sensor-geometry uncertainty, rather than treating node coordinates as exact.

The current RSSI-disturbance centroid may remain only as an explicitly experimental baseline. It must consume `GeometrySolution.positions`, not manually entered X/Y values.

---

# 6. UI/UX requirements

## 6.1 Remove normal manual X/Y card

Delete the normal Radar card that asks:

```text
Position of this node in array
x
y
Set position
```

The operator should instead see an automatic status card similar to:

```text
SENSOR GEOMETRY
3/3 nodes positioned
Mode: 2D AUTO
Quality: MEDIUM
Residual: 0.8 m
Updating automatically
```

When unresolved:

```text
SENSOR GEOMETRY
Estimating…
2 nodes discovered
1 valid ranging edge
Need additional independent ranging constraints
```

## 6.2 Radar

The Radar must:

- keep the local/operator node at the visual origin where appropriate;
- transform all solved array positions into the current local-node frame;
- display nodes with uncertainty regions when useful;
- display target uncertainty separately from sensor uncertainty;
- visually mark unresolved peers without placing them at `(0,0)`;
- update smoothly after geometry revisions.

## 6.3 Expert mode

Expose at minimum:

- per-node capability probes;
- ranging technology selected per peer;
- raw/filtered pairwise distances;
- measurement sigma;
- sample age;
- graph connected components;
- geometry state/dimension;
- solver residual;
- condition/observability indicator;
- used and rejected edges;
- frame ID/revision;
- manual override state;
- exact truth classification for each source.

## 6.4 Ground-truth mode

For lab validation only, Expert mode may provide a way to record known coordinates into a separate validation record.

Those coordinates must **not feed the production solver**.

---

# 7. Platform implementation work

## 7.1 Android full application

Implement native bridge functions for:

- runtime ranging capability enumeration;
- starting/stopping pairwise ranging sessions;
- Body Finder peer identity negotiation;
- normalized ranging result events;
- Wi-Fi Aware discovery/ranging where supported;
- Android 16 Ranging API where supported;
- optional UWB adapter where supported;
- BLE RSSI fallback;
- foreground lifecycle/permissions needed for sustained measurements;
- truthful error/status reporting.

The bridge must not crash on older Android versions when newer classes are unavailable.

## 7.2 Legacy Android

The legacy APK is a fallback sensor-node artifact for older devices.

It should contribute the strongest real capabilities available on that device, likely BLE and commodity radio measurements. If it cannot contribute a reliable pairwise range, advertise that limitation honestly while still participating in discovery/compute/display roles as supported.

The legacy app must not require manual coordinates merely to join the fabric.

## 7.3 Linux

Extend `body-finder-node` so geometry is automatic by default.

Remove required `--x/--y` from normal test commands.

Debug-only coordinate arguments may remain behind an explicit flag such as:

```text
--debug-ground-truth-x
--debug-ground-truth-y
```

and must never silently influence production geometry.

Implement real BLE/radio peer observations where platform support exists; otherwise advertise no ranging capability and participate through networking/compute.

## 7.4 Windows

Same semantics as Linux:

- no required manual X/Y;
- use real supported ranging/radio inputs;
- produce normalized observations;
- retain compute/network utility when RF access is limited.

## 7.5 WSL

The WSL test must prove truthful degradation:

- launches the Linux artifact;
- discovers/communicates if networking permits;
- reports direct RF unavailable if unavailable;
- never fabricates sensor/ranging measurements;
- can still consume and log the coordinator geometry solution.

---

# 8. Implementation phases and pull-request slicing

Each phase must be independently reviewable. Do not combine major sensing work with unrelated framework upgrades.

## Phase G0 — freeze semantics and tests

Deliver:

- this plan merged;
- protocol schema for ranging observations and geometry solution;
- unit-test fixtures for solved, underconstrained, disconnected, collinear and outlier graphs;
- explicit removal/deprecation plan for manual coordinates.

Gate:

- schemas round-trip;
- tests prove unknown position is distinct from `(0,0)`.

## Phase G1 — geometry core

Create/expand geometry module implementing:

- measurement graph;
- deterministic gauge selection;
- 1D/2D observability;
- robust optimization;
- uncertainty/residuals;
- stale edge handling;
- node join/leave.

Use deterministic synthetic fixtures **only for solver unit tests**, clearly marked simulation.

Gate:

- exact/simple synthetic triangles solve within numerical tolerance;
- noisy fixtures remain within expected error;
- outlier edge is down-weighted/rejected;
- collinear/disconnected fixtures return insufficient/degraded state;
- solution is deterministic under node-order permutations.

## Phase G2 — Android pairwise ranging foundation

Deliver native capability probes and a normalized pairwise-ranging event stream.

Priority:

1. Android 16 Ranging API when available;
2. Wi-Fi Aware RTT/WifiRttManager where available;
3. optional UWB;
4. BLE RSSI fallback.

Gate:

- app never labels a technology working until a real session/sample succeeds;
- all unsupported paths degrade without crash;
- peer persistent identity binds correctly to ranging session identity;
- recorded observations contain source + uncertainty + timestamps.

## Phase G3 — distributed geometry protocol

Deliver:

- ranging observations over the sensor fabric;
- coordinator graph aggregation;
- geometry solution publication;
- frame revisioning;
- hot add/remove;
- coordinator failover behavior.

Gate:

- protocol rejects stale/wrong-session data;
- all nodes converge on the same geometry revision or explicitly report staleness;
- failover does not substitute fabricated coordinates.

## Phase G4 — UI migration

Deliver:

- remove required X/Y fields from Radar;
- automatic geometry card;
- unresolved/degraded states;
- node uncertainty visualization;
- Expert ranging/solver diagnostics;
- exports updated to include geometry/ranging data.

Gate:

- a fresh install contains no normal workflow asking for sensor coordinates;
- scanning can begin without typing X/Y;
- unresolved geometry remains explicit rather than showing false positions.

## Phase G5 — Linux/Windows/WSL integration

Deliver automatic geometry participation and normalized logging across host platforms.

Gate:

- normal commands require no X/Y;
- WSL truthfully reports absent RF where applicable;
- Ubuntu/Windows consume published geometry and contribute measurements when available.

## Phase G6 — human-localization integration

Replace manual coordinate consumption with `GeometrySolution`.

Gate:

- target estimate cannot use stale/manual coordinates by accident;
- target covariance/uncertainty includes sensor geometry uncertainty;
- target localization degrades when geometry degrades.

## Phase G7 — release, documentation and physical test package

Update CI/release and physical-test documentation.

This phase ends only when a GitHub `dev-*` prerelease contains every required artifact listed below.

---

# 9. Required final prerelease artifacts

The release pipeline must fail if a mandatory artifact is missing.

## 9.1 Android

Mandatory:

```text
body-finder-ruview-universal.apk
body-finder-ruview.aab
body-finder-ruview-legacy-minsdk21.apk
```

The universal APK is the primary test artifact for Pixel-class/current Android devices.

The legacy APK is used only where the universal build cannot install or where old-API behavior must be tested.

## 9.2 Ubuntu / WSL

Mandatory:

```text
body-finder-node-linux-x86_64.tar.gz
body-finder-node-linux-x86_64.deb
```

The tarball must run on native Ubuntu and be usable inside WSL2 for the compute/network degradation test.

If ARM64 CI is added and verified, also publish:

```text
body-finder-node-linux-aarch64.tar.gz
body-finder-node-linux-aarch64.deb
```

but do not block the current x86_64 lab on ARM64.

## 9.3 Windows

Mandatory:

```text
body-finder-node-windows-x86_64.zip
```

## 9.4 Test/validation package

Mandatory:

```text
TESTING_AUTOGEOMETRY_RELEASE.md
release-manifest.json
capability-matrix.json
protocol-version.txt
ruview-upstream-lock.json
model-manifest.json
SHA256SUMS
SBOM.spdx.json
```

Recommended:

```text
body-finder-validation-tools.zip
protocol-fixtures.zip
autogeometry-example-report.json
```

`body-finder-validation-tools.zip` should contain helper scripts for collecting logs, checking manifests/checksums and packaging returned results. It must not contain fake sensor data presented as live data.

## 9.5 Release manifest requirements

`release-manifest.json` must include at least:

```json
{
  "release": "dev-N",
  "commit": "...",
  "classification": "EXPERIMENTAL_AUTOGEOMETRY_PHYSICAL_VALIDATION_BUILD",
  "manual_node_coordinates_required": false,
  "automatic_geometry": true,
  "through_wall_validated": false,
  "human_localization_validated": false,
  "artifacts": [],
  "protocol_version": 2
}
```

Do not claim through-wall detection/localization is validated merely because automatic sensor geometry works.

---

# 10. CI/release gates

The release workflow must not publish a test prerelease unless all mandatory jobs pass.

Required CI checks:

1. Rust workspace tests.
2. geometry solver fixtures/tests.
3. protocol schema/serialization tests.
4. Android TypeScript compile.
5. Android native compile for minimum and current supported API paths.
6. Android release APK build.
7. Android AAB build.
8. legacy Android APK build.
9. Linux release build/package.
10. Windows release build/package.
11. artifact-presence check.
12. release-manifest validation.
13. SHA-256 generation.
14. SPDX SBOM generation.
15. grep/static guard preventing normal UI copy such as `Set position` / mandatory X/Y controls.
16. CLI guard ensuring normal Linux/Windows test invocation does not require `--x`/`--y`.

A CI test cannot prove RF accuracy; therefore the release remains `EXPERIMENTAL_*` until physical validation data is returned.

---

# 11. New physical-test protocol

Replace the existing coordinate-entry test protocol for automatic-geometry releases.

## 11.1 Lab devices

Primary current lab:

- Pixel 7 Pro;
- Pixel 10 Pro;
- Lenovo Tab2;
- optional fourth Android;
- native Ubuntu x86_64;
- WSL2 on Windows;
- Windows native host.

The application must not rely on these exact model names; they are only the available test devices.

## 11.2 Test setup

For the automatic-geometry acceptance test:

1. install the release artifacts;
2. place 3–4 Android devices in a non-collinear physical arrangement where possible;
3. optionally include native Ubuntu/Windows nodes;
4. **do not enter node coordinates into any app**;
5. allow automatic discovery/ranging/geometry to run;
6. separately measure the real node-to-node distances and/or coordinates with a tape measure for validation only;
7. store the manual measurements in `ground-truth.txt` after/beside the test, not in the running app.

## 11.3 Automatic geometry acceptance sequence

### Test A — discovery only

Expected:

- node count converges;
- peer identities remain stable;
- no X/Y prompt appears.

### Test B — ranging capability negotiation

Expected:

- each node records which technologies were actually probed;
- selected technology is visible per edge;
- unsupported technologies remain unsupported/unavailable, never simulated.

### Test C — 2-node baseline

Start with two suitable nodes.

Expected:

- if a real pairwise distance exists, state may become `GEOMETRY_1D`;
- if not, state remains `GEOMETRY_INSUFFICIENT`;
- no fabricated 2D coordinates.

### Test D — 3-node automatic 2D geometry

Add a third non-collinear node.

Expected when constraints are sufficient:

- state becomes `GEOMETRY_2D`;
- all solved coordinates are generated automatically;
- no manual coordinate input;
- solver exports residual and uncertainty.

If the hardware/API combination cannot produce sufficient independent constraints, the correct result is `GEOMETRY_INSUFFICIENT`, with logs that identify exactly which edge/capability is missing.

### Test E — fourth-node redundancy

Add fourth node.

Expected:

- graph obtains redundant edges where possible;
- solver quality should normally improve or stay defensibly similar;
- a bad edge can be identified without destroying the entire solution.

### Test F — node movement

Move one sensor a known distance while keeping others fixed.

Expected:

- geometry revision increments;
- moved node estimate changes;
- stale old geometry is not silently frozen;
- uncertainty grows during transition and falls after convergence if measurements support it.

### Test G — node removal/rejoin

Expected:

- graph reconfigures;
- remaining geometry persists if still observable;
- otherwise state degrades explicitly;
- rejoining node is reacquired automatically.

### Test H — coordinator failover

Expected:

- new coordinator rebuilds/continues geometry from valid measurements;
- frame revision/transform is explicit;
- no manual recalibration request solely because coordinator changed.

### Test I — empty-scene human control

Only after sensor geometry is stable:

- calibrate empty scene;
- collect at least 60 s;
- verify no automatic geometry measurement is mislabeled as human evidence;
- record false-positive candidates.

### Test J — one-person LOS

Use externally measured ground truth for the person.

Expected:

- target estimate consumes automatic sensor geometry;
- exported uncertainty includes geometry uncertainty;
- no hidden use of ground-truth sensor coordinates.

### Test K — one-wall experiment

Only after LOS works and only in a safe stable environment.

No negative result may be interpreted as proof that no human exists.

---

# 12. Required returned test data

The release documentation must ask the tester to return a ZIP similar to:

```text
autogeometry-test/
  android-pixel7pro.json
  android-pixel10pro.json
  android-lenovo.json
  android-4.json                 # optional
  ubuntu-native.jsonl
  wsl.jsonl
  windows-host.jsonl
  ground-truth.txt
  screenshots/
  release-manifest.json
  SHA256SUMS
```

Each Android export must contain:

- build/release/commit;
- node ID/session ID;
- device/runtime capability probes;
- discovered peers;
- ranging capabilities;
- raw/filtered pairwise observations;
- observation source technology;
- sigma/quality/age;
- geometry graph summary;
- geometry solution with frame/revision;
- node position covariance/error regions;
- rejected edges and reasons;
- calibration status;
- human estimate if any;
- explicit flags showing whether manual overrides were used.

`ground-truth.txt` should contain data the app did **not** receive, for example:

```text
Test area dimensions: ...
Physical node layout measured externally: ...
Pairwise tape distances: A-B=..., A-C=..., B-C=...
Height differences if relevant: ...
Empty interval: ...
LOS person position relative to chosen physical reference: ...
Wall case position/material/thickness: ...
Nodes moved during test: ...
Manual geometry override used in app: NO
```

---

# 13. Validation metrics

Automatic geometry must be evaluated separately from human localization.

## 13.1 Geometry metrics

Calculate where ground truth exists:

- pairwise distance error after solving;
- node-position error after optimal rigid alignment to ground truth;
- median/mean/95th-percentile position error;
- residual RMS;
- graph connectivity;
- edge availability rate;
- ranging sample success rate;
- geometry convergence time;
- position jitter while devices are stationary;
- response to a moved node;
- uncertainty coverage: fraction of true positions inside reported 95% region.

Because the internal frame has arbitrary rotation/translation/reflection gauge, compare solved geometry to ground truth only after an appropriate rigid alignment. Do not penalize arbitrary global origin/orientation.

## 13.2 Technology-specific reporting

Report metrics grouped by ranging source:

```text
UWB
BLE Channel Sounding
Wi-Fi Aware / NAN RTT
Wi-Fi AP RTT
BLE RSSI
mixed-source graph
```

Do not blend all technologies into one accuracy claim.

## 13.3 Release acceptance philosophy

The first automatic-geometry prerelease is a **measurement/validation build**, not a claim that all commodity devices will meet a fixed accuracy.

A physically tested device combination may be classified after data collection as:

```text
AUTO_GEOMETRY_HIGH
AUTO_GEOMETRY_MEDIUM
AUTO_GEOMETRY_LOW
AUTO_GEOMETRY_INSUFFICIENT
```

Thresholds must be based on measured data and uncertainty calibration, not marketing targets.

---

# 14. Safety and truth policy additions

1. Automatic does not mean accurate; every solution needs uncertainty.
2. Failure to solve geometry must remain visible.
3. BLE RSSI must not be relabeled as UWB/RTT/CSI.
4. Connected Wi-Fi RSSI must not be called inter-node ranging without validation.
5. Ground truth must not leak into the live estimator during acceptance tests.
6. A synthetic solver test may verify math but cannot validate physical ranging.
7. A successful geometry test does not validate human detection.
8. A successful LOS human test does not validate through-wall rescue performance.
9. A negative RF scan does not prove absence of a human.
10. The product remains experimental until independently validated on the exact capability path.

---

# 15. Definition of done for this plan

This plan is complete only when the following end state exists on `main` and a corresponding `dev-*` prerelease is published:

- [ ] Normal Android UI never asks the operator to enter node X/Y/Z.
- [ ] Normal Linux/Windows startup never requires X/Y/Z.
- [ ] Nodes discover each other automatically.
- [ ] Real ranging capabilities are probed dynamically.
- [ ] Pairwise ranging observations have source, timestamp and uncertainty.
- [ ] Coordinator builds a measurement graph.
- [ ] Solver produces 1D/2D/3D only when observable.
- [ ] Three nodes are not automatically treated as sufficient unless constraints support 2D.
- [ ] Geometry is robustly optimized and includes uncertainty.
- [ ] Node join/leave/movement triggers automatic refinement.
- [ ] Coordinator failover preserves or explicitly re-frames geometry.
- [ ] Human localization consumes automatic geometry, not typed coordinates.
- [ ] Expert mode exposes source/provenance/residuals/rejected edges.
- [ ] APK builds successfully.
- [ ] AAB builds successfully.
- [ ] Legacy APK builds successfully.
- [ ] Ubuntu/WSL x86_64 tarball builds successfully.
- [ ] Ubuntu x86_64 `.deb` builds successfully.
- [ ] Windows x86_64 ZIP builds successfully.
- [ ] `TESTING_AUTOGEOMETRY_RELEASE.md` is included.
- [ ] Release manifest explicitly says manual node coordinates are not required.
- [ ] SHA-256 checksums and SPDX SBOM are included.
- [ ] CI fails on missing mandatory artifacts.
- [ ] GitHub publishes a `dev-*` prerelease containing all mandatory artifacts.
- [ ] The physical-test instructions never ask the tester to enter sensor coordinates into the app.
- [ ] Returned logs contain enough data to independently verify geometry accuracy and uncertainty.

---

# 16. Recommended execution order for Codex

Codex should execute this plan in small PRs in this order:

```text
PR G0  contracts + fixtures + locked semantics
PR G1  robust geometry solver
PR G2  Android ranging capability adapters
PR G3  distributed ranging graph + geometry publication
PR G4  remove manual-coordinate UI + Expert diagnostics
PR G5  Linux/Windows/WSL participation
PR G6  human-localization integration with geometry covariance
PR G7  release workflow + test package + final dev prerelease
```

For each PR:

1. read this plan and the existing master implementation plan;
2. inspect current code before changing it;
3. preserve truth classifications;
4. add tests before/with implementation;
5. run the complete relevant test suite;
6. do not merge if a capability is simulated but labeled live;
7. update documentation/protocol version if wire semantics change;
8. keep the release build reproducible;
9. record any hardware/API limitation discovered during implementation;
10. never reintroduce mandatory manual coordinates as a shortcut.

---

# 17. Final expected operator experience

The intended test/operator flow after implementation is:

```text
INSTALL / OPEN APP
        ↓
GRANT REQUIRED LOCAL RADIO PERMISSIONS
        ↓
NODES DISCOVER EACH OTHER
        ↓
APP PROBES REAL RANGING CAPABILITIES
        ↓
PAIRWISE RANGING STARTS AUTOMATICALLY
        ↓
SENSOR GEOMETRY IS SOLVED AUTOMATICALLY
        ↓
UI SHOWS GEOMETRY QUALITY + UNCERTAINTY
        ↓
CALIBRATE EMPTY SCENE
        ↓
START HUMAN SEARCH
        ↓
TARGET ESTIMATE USES AUTO-GEOMETRY
        ↓
EXPORT COMPLETE VALIDATION JSON/JSONL
```

At no point in the normal flow should the operator have to decide or type where a sensor node is located.
