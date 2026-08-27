# ADR-PIXEL10-PEER-CONTINUITY-ROOT-CAUSE

**Status:** Accepted for dev-19 hardening  
**Scope:** immediate peer-expiry mechanism and false-PASS defect; upstream jitter origin remains open.

## Evidence

In dev-18 second campaign, Pixel 10 Pro/API 37 ran 379283 ms and started with 2 expected peers. It recorded 28 UDP peer expiries, ended with one peer `EXPIRED` at approximately 6895 ms since last RX, and nevertheless reported `all_expected_peer_metric_uptime_percent≈94.57%` after the live expected cohort had fallen to 1. The service remained RUNNING, screen ON, Battery Saver OFF, wake/Wi-Fi/multicast locks held and app active.

Source inspection shows dev-18 removes a UDP peer when `now-last_seen > 5000ms` and then removes its last valid range. Therefore a measured ~6895 ms local RX gap deterministically becomes an expiry. Separately, validation uptime used the current active peer count as the expected denominator, allowing the denominator to shrink from 2 to 1.

## Classification

- **H2 — peer expiry too aggressive for observed transient jitter:** supported as the immediate expiry mechanism.
- **H5 — expected-peer model uses mutable active cohort:** confirmed.
- **H1 RangingManager causes the loss:** not confirmed.
- **H3 multicast/broadcast reception origin:** not confirmed.
- **H4 scanner restart origin:** not confirmed.
- **H6 BLE/UDP coupling origin:** not confirmed.

## Decision

1. Freeze expected peer IDs/count at validation Start; all expected-peer uptime and acceptance gates use that immutable cohort.
2. Require exactly 2 expected peers before a 3-node acceptance run starts.
3. Replace one-step 5 s peer eviction with diagnostic state machine:
   - `ACTIVE` while RX gap <= 5000 ms;
   - `STALE` for gap >5000 ms and <=10000 ms;
   - `EXPIRED` only after >10000 ms.
4. The 10000 ms hard bound is not extended: it reuses the already-frozen continuity hard boundary and covers the demonstrated ~6895 ms transient. Any future increase requires new measured gap evidence and a separate ADR.
5. Export run-scoped `PEER_BECAME_STALE`, `PEER_EXPIRED`, `PEER_REACTIVATED` events with RX gap, last RX, packet count, scanner generation, ranging state, BLE sample age, fabric state and lifecycle state.
6. Do not disable or blame API36+ `RangingManager` without a controlled physical A/B.

## Safety properties

The change does not modify BLE calibration, range estimator, recovery budget/timings, reciprocal fusion or automatic geometry. A stale peer is still visible as `STALE`; it is never mislabeled `ACTIVE` in fabric diagnostics, and any hard expiry remains a strict acceptance failure.
