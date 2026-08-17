# Body Finder – RuView automatic-geometry release: complete physical test protocol

> **Purpose:** validate the `dev-*` prerelease that implements protocol v2 automatic sensor geometry.  
> **Safety:** experimental research software. **Not validated for rescue use.** A negative RF result never proves that no person is present. Do not test inside unstable structures or real collapse hazards.  
> **Critical rule:** **never enter measured node coordinates into the application.** Sensor ground truth is recorded only after the application has produced its automatic solution and is kept in a separate validation file.

---

## 1. Download these artifacts from the same `dev-*` release

Required for the current lab:

- `body-finder-ruview-universal.apk` — full Android application for modern Android devices.
- `body-finder-ruview-legacy-minsdk21.apk` — fallback sensor node for old Android devices such as devices that cannot install the full Expo build.
- `body-finder-ruview.aab` — Android bundle build verification artifact.
- `body-finder-node-linux-x86_64.tar.gz` — native Ubuntu and WSL2 executable.
- `body-finder-node-linux-x86_64.deb` — Ubuntu amd64 package alternative.
- `body-finder-node-windows-x86_64.zip` — native Windows executable.
- `body-finder-ruview-ios-simulator.zip` — unsigned iOS Simulator build-validation artifact; requires macOS/Xcode and is **not** an installable physical-device IPA.
- `body-finder-validation-tools.zip` — validator, ground-truth template and protocol fixtures.
- `TESTING_AUTOGEOMETRY_RELEASE.md` — this file.
- `capability-matrix.json`, `release-manifest.json`, `protocol-version.txt`, `ruview-upstream-lock.json`, `model-manifest.json`.
- `SBOM.spdx.json` and `SHA256SUMS`.

All artifacts used in one test run must come from the **same release tag**.

---

## 2. Verify artifact integrity

### Ubuntu / WSL

Put the downloaded files in one directory and run:

```bash
sha256sum -c SHA256SUMS
```

Every downloaded file listed in the checksum file should report `OK`.

### Windows PowerShell

For a file, compare:

```powershell
Get-FileHash .\body-finder-node-windows-x86_64.zip -Algorithm SHA256
```

with the corresponding entry in `SHA256SUMS`.

Do not continue with an artifact whose digest differs.

---

## 3. Recommended physical lab

Current recommended minimum:

```text
Pixel 10 Pro       full APK
Pixel 7 Pro        full APK
Lenovo / old Android full APK if installable, otherwise legacy APK
Native Ubuntu      Linux node
Windows host       Windows node
WSL2               Linux node, compute/degradation test
```

A fourth Android may be added and is strongly recommended for redundancy testing.

All participating network nodes should use the same local Wi-Fi/LAN for UDP discovery. Internet is not required after the artifacts are downloaded. Bluetooth must be enabled on Android devices used for automatic geometry.

**Do not place the phones at coordinates chosen from this document.** Place them around a safe test area in a non-collinear layout. Do not measure or enter their coordinates yet.

---

# PART A — INSTALLATION AND PLATFORM SANITY

## 4. Full Android app — Pixel 10 Pro / Pixel 7 Pro / other supported Android

For each modern Android device:

1. Enable Bluetooth and Wi-Fi.
2. Connect it to the same local Wi-Fi as the other nodes.
3. Install:

```bash
adb install -r body-finder-ruview-universal.apk
```

or copy the APK to the device and open it.

4. Launch **Body Finder – RuView**.
5. Grant requested Nearby Wi-Fi/location/Bluetooth permissions. On Android 16/API 36+, grant the ranging permission if the OS requests it.
6. Verify that **there are no X/Y/Z fields and no `Set position` / `Guardar posición` action**.
7. Open **Expert** and capture a screenshot of `Capabilities`.
8. Confirm `CSI` is not falsely marked working.
9. Confirm `manual_geometry_override` is `false` in the exported data.

Expected on the modern Android build: BLE peer ranging should become `WORKING_DEGRADED` when BLE scanning is active and permissions/hardware permit it. The actual range observations must identify their source as `BLE_RSSI` unless a future verified higher-quality adapter reports another technology.

## 5. Legacy Android fallback — Lenovo / old Android

Use this only when the full APK cannot install or run reliably:

```bash
adb install -r body-finder-ruview-legacy-minsdk21.apk
```

Then:

1. Enable Wi-Fi + Bluetooth.
2. Grant requested permissions.
3. Verify the screen says automatic geometry and contains **no coordinate inputs**.
4. Leave the app open.
5. Confirm `peers` rises when other nodes are running.
6. Confirm `range edges` becomes non-zero if it receives Body Finder BLE advertisements.
7. Use **SHARE SNAPSHOT JSON** and save the result.

The legacy APK does not have the Radar UI; it is a sensor/fabric fallback node.

## 6. Native Ubuntu

Extract and run:

```bash
mkdir -p bf-ubuntu
cd bf-ubuntu
tar xzf ../body-finder-node-linux-x86_64.tar.gz
chmod +x body-finder-node
./body-finder-node --node ubuntu-native --calibrate 10 --record ubuntu-native.jsonl
```

Alternative `.deb` installation:

```bash
sudo dpkg -i body-finder-node-linux-x86_64.deb
body-finder-node --node ubuntu-native --calibrate 10 --record ubuntu-native.jsonl
```

Important: there are intentionally **no `--x` or `--y` arguments**.

Expected:

- one JSON status line per cycle;
- `protocol_version = 2`;
- `position = null` in the node advertisement;
- `manual_geometry_override = false`;
- peer count increases when compatible nodes are visible on the LAN;
- Ubuntu may solve geometry from range edges contributed by Android peers even if Ubuntu itself cannot produce a native pairwise range;
- unavailable RF capabilities remain unavailable rather than being synthesized.

## 7. Native Windows

PowerShell:

```powershell
Expand-Archive .\body-finder-node-windows-x86_64.zip -DestinationPath .\bf-win -Force
cd .\bf-win
.\body-finder-node.exe --node windows-host --calibrate 10 --record windows-host.jsonl
```

Expected behavior is analogous to Ubuntu. Windows may expose a real connected-WLAN link metric, but that value is human-presence experimental evidence only; it is not treated as a phone-to-phone distance.

## 8. WSL2

Inside WSL2:

```bash
mkdir -p ~/bf-wsl
cd ~/bf-wsl
tar xzf /path/to/body-finder-node-linux-x86_64.tar.gz
chmod +x body-finder-node
./body-finder-node --node wsl --calibrate 10 --record wsl.jsonl
```

Expected:

- platform identifies as `wsl`;
- lack of direct Wi-Fi/BLE access is acceptable and must be reported truthfully;
- it can still exercise protocol/compute/network behavior where WSL networking allows it;
- if UDP broadcast/multicast does not traverse WSL networking, record that result and rely on the Windows host node for the Windows machine's field-network participation.

## 9. iOS Simulator build validation — macOS/Xcode

This release includes an unsigned simulator `.app`, not a signed device IPA. On a Mac with Xcode:

```bash
unzip body-finder-ruview-ios-simulator.zip -d bf-ios
xcrun simctl boot "iPhone 16 Pro" 2>/dev/null || true
open -a Simulator
APP=$(find bf-ios -name '*.app' -maxdepth 3 | head -1)
xcrun simctl install booted "$APP"
xcrun simctl launch booted com.trochez.bodyfinderruview
```

Validate:

1. app launches;
2. no manual node-coordinate input exists;
3. Expert truth data marks simulator BLE/RF limitations honestly;
4. protocol version is 2;
5. automatic geometry remains insufficient instead of inventing sensor coordinates.

**Physical iPhone/iPad RF participation is not claimed by this artifact.** A signed IPA/TestFlight build and physical iOS ranging/fabric validation require Apple signing credentials and a physical iOS lab device; the simulator artifact is strictly build/UI/truth validation.

---

# PART B — AUTOMATIC SENSOR GEOMETRY

## 10. Prepare the three-Android geometry test

Use three Android nodes first. Recommended: Pixel 10 Pro + Pixel 7 Pro + Lenovo/third Android.

1. Put the three devices around an empty safe test zone.
2. Keep the layout non-collinear; a rough triangle is sufficient.
3. Keep every device stationary.
4. Start Body Finder on all three.
5. **Do not measure, type, or import sensor coordinates.**
6. Wait until each device discovers peers and begins reporting pairwise range observations.
7. In **Expert**, confirm range observations contain:
   - observer node ID;
   - peer node ID;
   - technology;
   - distance;
   - sigma/uncertainty;
   - RSSI when applicable;
   - source detail.
8. Watch the geometry state.

Expected progression when the measurement graph is sufficient:

```text
GEOMETRY INSUFFICIENT
        ↓
GEOMETRY 1D          # possible while only one defensible baseline exists
        ↓
GEOMETRY 2D or GEOMETRY DEGRADED
```

Three discovered nodes do **not** guarantee 2D geometry. If independent edges are missing or the layout is degenerate, `GEOMETRY INSUFFICIENT` is the correct result.

## 11. Explicit node-count/observability test

Perform this before the human-detection scenarios.

### 11.1 One node

Run only one Android app.

Expected: no fabricated array layout; geometry insufficient/unknown.

### 11.2 Two nodes

Start a second Android and keep both stationary.

Expected when a valid range edge exists: at most a **1D baseline**. The app must not fabricate a triangle or 2D solution.

### 11.3 Three nodes

Start the third Android in a non-collinear physical position.

Expected: 2D only if enough independent range constraints exist. Otherwise the reason must be visible in Expert mode.

### 11.4 Four nodes, if available

Add a fourth Android without restarting the session.

Expected: it is incorporated automatically when observable; redundant range edges should improve robustness or at least expose outliers rather than forcing them into the solution.

Save a shared JSON from every full Android at the end of each subtest.

## 12. Ground-truth geometry — measure only AFTER automatic solving

After the three/four-node automatic geometry has stabilized:

1. Do not move the devices.
2. On each app, open Expert and record its exact `node_id`.
3. Choose an arbitrary external physical origin only for validation; for example, the location of one device may be `(0,0)` on your paper/measurement sheet.
4. With a tape measure, measure the physical X/Y positions of all sensor devices relative to that external origin, or measure enough pairwise distances to reconstruct them.
5. Copy `GROUND_TRUTH_TEMPLATE.json` from `body-finder-validation-tools.zip` to the scenario directory.
6. Fill `node_positions_m` using the **exact node IDs** from the app exports.
7. Do **not** enter those values back into Body Finder.

The validation script aligns the arbitrary automatic frame with the external ground-truth frame using the automatic geometry's anchor/axis; it also tests the mirrored orientation and chooses the orientation that minimizes sensor error. This prevents an arbitrary coordinate gauge from being mistaken for localization error.

---

# PART C — HUMAN-PRESENCE / LOCALIZATION VALIDATION

## 13. Empty-scene control

With sensor devices fixed:

1. Keep the target area empty.
2. On every full Android tap **Calibrate empty scene**.
3. Keep the area empty during calibration.
4. Start scan on each calibrated full Android. Calibrate/start the legacy node too if used.
5. Record for **60 seconds** without anybody entering the target area.
6. Save screenshots of Radar + Expert.
7. Export JSON from each Android.
8. Keep Ubuntu/Windows/WSL JSONL recording.

Acceptance data to inspect:

- false `POSSIBLE_HUMAN` / `PROBABLE_HUMAN` events;
- geometry stability/jitter;
- range-edge stability;
- geometry residual/condition;
- whether any stale/unresolved node was incorrectly drawn as positioned.

## 14. One-person line-of-sight (LOS) test

Do not move sensors after the empty baseline.

1. Mark a safe physical target point in the test area.
2. Measure its external X/Y coordinate and add it to `person_position_m` in a copy of the ground-truth file for this scenario.
3. Have one person stand at that point.
4. Stay mostly still for **60 seconds**.
5. Then move gently within approximately 1 m for **30 seconds**.
6. Save Android JSON exports and screenshots.
7. Keep native JSONL recordings.
8. Record exact local start/end times in the ground-truth file.

The target coordinate is validation data only; never enter it in the app.

## 15. One stable wall test

Only after the LOS test works as an instrumented experiment:

1. Use a normal, stable wall — never rubble or an unsafe structure.
2. Keep all sensor devices fixed.
3. Record wall material and approximate thickness.
4. Calibrate/record an empty 30-second control if environmental conditions changed.
5. Put one person at a measured external point behind the wall.
6. Record for **60 seconds**.
7. Export the same JSON/JSONL/screenshots.
8. Record wall metadata and target point externally.

A failed/weak result must remain weak/failed. Do not reinterpret it as proof that nobody is present.

---

# PART D — DYNAMIC FABRIC / FAILURE TESTS

## 16. Node movement and automatic re-geometry

With a solved 3+ node geometry:

1. Record a stable 30-second interval.
2. Move exactly one sensor device approximately 1–2 m to a new safe location.
3. Do not enter its new position anywhere.
4. Observe range-edge changes and geometry revisions.
5. Wait for the solver to converge/degrade based on real evidence.
6. Measure the new physical position only after the automatic update.
7. Export results.

Pass condition: old coordinates are not silently treated as exact current coordinates. The solution must update, degrade, become insufficient, or mark uncertainty accordingly.

## 17. Node removal / rejoin

1. With 3+ nodes active, close one Android app.
2. Observe peer expiration and geometry response.
3. Reopen it without re-entering any geometry data.
4. Confirm the same persistent node identity returns on that installation.
5. Confirm the node is automatically reintegrated when range/network evidence is sufficient.

## 18. Coordinator failover

1. Record the current coordinator node ID.
2. Stop that coordinator.
3. Confirm another eligible node is deterministically elected.
4. Verify the geometry is recomputed/preserved from available measurement evidence rather than replaced by defaults.
5. Export the result.

## 19. RF-degraded node participation

Run native Ubuntu, Windows and WSL while Android geometry is active.

Verify that a compute/network node without a real pairwise ranging adapter:

- does not invent a range to peers;
- may remain unresolved as a sensor position;
- can still receive/compute a geometry solution from range observations published by capable nodes;
- clearly exposes its own capability limitation.

---

# PART E — FILES TO SAVE

## 20. Recommended result directory

Create one directory per scenario:

```text
results/
  01-geometry-3nodes/
  02-geometry-4nodes/
  03-empty/
  04-los-still/
  05-los-moving/
  06-wall/
  07-node-moved/
  08-node-removed-rejoined/
  09-coordinator-failover/
```

Each applicable scenario should contain:

```text
ground-truth.json
android-pixel10pro.json
android-pixel7pro.json
android-lenovo-or-third.json
android-fourth.json                  # if used
legacy-android.json                  # if legacy APK used
ubuntu-native.jsonl
windows-host.jsonl
wsl.jsonl
screenshots/
notes.txt
```

Use the share action after the relevant interval. If the Android share target only gives text, save that text verbatim as `.json`.

## 21. Ground-truth file

Use the included `GROUND_TRUTH_TEMPLATE.json`.

Minimum fields to fill:

- scenario/test ID;
- exact node IDs and measured external sensor coordinates;
- target coordinate when a person is present;
- start/end local timestamps;
- wall metadata if relevant;
- what moved, if anything.

Again: ground truth remains outside the application.

---

# PART F — AUTOMATIC VALIDATION

## 22. Run the included validator

Extract:

```bash
unzip body-finder-validation-tools.zip -d bf-validation
```

For a scenario directory:

```bash
python3 bf-validation/validate_autogeometry.py results/01-geometry-3nodes \
  --ground-truth results/01-geometry-3nodes/ground-truth.json \
  --output results/01-geometry-3nodes/validation-summary.json
```

The validator reports, where data permits:

- protocol version consistency;
- any `manual_geometry_override=true` violation;
- geometry state/dimension;
- number of solved nodes;
- used/rejected range edges;
- technologies observed;
- solver residual and condition;
- node-position error after aligning the automatic frame to external ground truth;
- node RMSE/max error;
- pairwise-distance RMSE;
- target error after the same frame alignment when a target estimate + target ground truth exist;
- whether the reported target 95% error radius covered the physical target.

Run it for every scenario that has ground truth.

---

# PART G — WHAT TO RETURN FOR REVIEW

## 23. Package the complete result

Ubuntu/WSL:

```bash
zip -r body-finder-autogeometry-test-results.zip results/
```

Send that ZIP for analysis.

The minimum useful acceptance result is:

1. three Android geometry test;
2. empty-scene control;
3. one-person LOS still + moving;
4. native Ubuntu JSONL;
5. Windows JSONL;
6. WSL JSONL or explicit WSL networking/RF failure evidence;
7. at least one node removal/rejoin test;
8. all associated ground truth and screenshots.

A fourth Android, wall test and coordinator failover make the result substantially stronger.

---

# 24. Expected acceptance principles

The release passes the **software/measurement plumbing** acceptance only if:

- no normal flow requires manual X/Y/Z;
- protocol v2 is consistent across peers;
- real pairwise ranging observations preserve source and uncertainty;
- 2D is reported only when independently observable;
- missing/degenerate geometry is represented as insufficient/degraded;
- unresolved nodes are not silently placed at zero/default coordinates;
- node join/leave/movement causes automatic graph/geometry adaptation;
- connected Wi-Fi RSSI is never relabeled as pairwise phone distance or CSI;
- simulated/fabricated measurements are never labeled live;
- exported reports contain enough provenance to reproduce the decision.

**Human-through-wall performance remains a separate empirical question.** Do not promote the build to a rescue claim solely because the software acceptance tests pass.
