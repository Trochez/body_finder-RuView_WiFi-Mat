# Post-dev17 → v1 implementation status

## Implemented in dev-18

- dev-17 physical acceptance frozen as machine-readable baseline and CI gate (EPIC A software scope).
- SessionManifest v1, RFMeasurement v1 and GroundTruth v1 schemas (B001/B002/B012-B014/B016).
- Deterministic recorder/replay/validation core with round-trip, monotonic-time and corruption checks (B003/B004/B008-B011/B015).
- Ubuntu native connected-Wi-Fi RSSI recorder with BSSID/frequency provenance when exposed by `iw`; Windows native `netsh` adapter; explicit WSL degraded semantics; CSI remains capability-truth `UNSUPPORTED` unless verified (C021/C022/C024-C030 software scope).
- Existing Android runtime remains the authoritative BLE/autogeometry acquisition path and already exports self-contained validation JSON. dev-18 packages the same cross-platform runtime with version bump and no human-detection claim.
- Empty-room calibration statistics and inspectable feature primitives (mean/median/variance/std/MAD, delta, change score, lag-1 autocorrelation, spectral-energy proxy) are implemented in `body-finder-science` with deterministic tests (D004-D008, E002-E013 foundational subset).
- Release artifacts include replay/validator/recorder CLIs, schemas, SBOM, checksums, test guide and frozen baseline.

## Intentionally not claimed PASS

The attached plan explicitly forbids simulation-as-proof and requires labelled/blind physical evidence. Therefore dev-19+ human detection, RTI localization, uncertainty calibration, tracking, through-wall, safe-rubble, physical iOS parity and `v1.0.0` acceptance remain blocked until those campaigns are executed. `humanScanningEnabled=false`, `humanLocalizationValidated=false`, and `rescueUseValidated=false` remain mandatory.

## Next gate

Run `docs/TESTING_DEV18.md`, return the JSON/JSONL evidence, then derive thresholds from the physical dataset and proceed to dev-19 without leakage into the blind partition.
