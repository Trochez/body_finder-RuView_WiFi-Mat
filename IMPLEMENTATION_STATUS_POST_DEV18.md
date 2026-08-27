# IMPLEMENTATION STATUS POST DEV18 — dev19

## Implemented

- dev-19 versioning (`0.2.0-experimental.19`) via deterministic source patch.
- Pixel 10 peer continuity hardening: `ACTIVE -> STALE (5s) -> EXPIRED (>10s)`.
- immutable 2-peer validation cohort captured at Start.
- strict preflight requires 2 peers for 3-node acceptance.
- expected-peer uptime can no longer normalize 2 -> 1.
- run-scoped self-contained fabric causal timeline (`PEER_BECAME_STALE`, `PEER_EXPIRED`, `PEER_REACTIVATED`).
- event context includes UDP RX age/count, monotonic/wall timestamps, scan generation, RangingManager state/yield, BLE sample age, socket/multicast state and lifecycle diagnostics.
- strict dev19 validator with G0-G11 gates and event/counter reconciliation.
- dev18 second-run compact regression summary and Pixel10 reconstruction.
- ADRs for roadmap shift and evidence-bounded root cause.
- release workflow for Android universal APK/AAB, legacy APK, Linux, Windows, validators, SBOM, SHA256, manifest and redownload verification.
- detailed test procedure in `docs/TESTING_DEV19.md`.

## Frozen / unchanged

Protocol 2; snapshot schema 4; `android-ble-lab-v1`; RSSI@1m -69.19 dBm; path-loss exponent 3.62; calibrated 0.5–5.0 m domain; range fresh 5 s / hard 10 s; recovery budget 3/300000 ms; recovery/probe timing limits; system-ranging BLE yield 120000 ms; reciprocal fusion; automatic geometry; manual override false; all human/rescue validation flags false.

## Acceptance status

CI/build/release gates are automated. Final physical 3-Android acceptance is **PENDING USER CAMPAIGN** because it requires the actual Pixel 10 Pro, Pixel 7 Pro and Lenovo TB-J606L in the same RF/LAN environment for >=330 s. No software result may fabricate that evidence.

Human/no-human work remains blocked until all three dev19 JSON exports pass `validate_dev19_session.py` with `peer_expire_delta=0` and all other hard gates.
