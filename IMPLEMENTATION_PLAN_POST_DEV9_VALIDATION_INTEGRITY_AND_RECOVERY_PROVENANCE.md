# Body Finder – RuView — Post-dev-9 validation integrity and recovery provenance

Baseline `a2cdadd0d0055f0787c85d414d3c07d98810f1c9`; target `dev-10 / 0.2.0-experimental.10`; protocol 2. Recommended team: 8 logical roles (TL, Android BLE, Validation/Protocol, RF Reliability, Mobile UX, QA Automation, DevOps/Release, Field Validation).

## Frozen invariants
android-ble-lab-v1; RSSI@1m -69.19; n 3.62; domain 0.5–5m; minSamples 3; fresh 5s; holdover/hard expiry 10s; sigma aging 0.15m/s; FILTERED_PRIMARY; UNFILTERED_RECOVERY; stall 5s; cooldown 30s; max 3 attempts/5min; API36 BLE yield 120s; human/rescue false.

## Implemented backlog
Immutable completed validation snapshot and atomic End; run-scoped recovery/suppression/ranging counters; bounded event timeline; unambiguous logical strategy/ScanSettings/filter provenance; per-peer stall/recovery provenance; RangingManager correlation; Expert truth correction; report/schema/contracts; CI/release dev-10; detailed two-export physical retest and comparator.

## DoD
CI matrix green, release dev-10 with Android universal/AAB/legacy, Linux/Windows node, iOS simulator, fixtures/tools/schema/manifest/SBOM/SHA256, then 3-device physical retest: usable metric>=90%, Geometry2D>=90%, peer expiry 0 and immutable Export1==Export2 snapshot on 3/3. Human scanning remains disabled.
