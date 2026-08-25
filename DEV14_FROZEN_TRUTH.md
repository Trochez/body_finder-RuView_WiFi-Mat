# DEV14 Frozen Truth

- Build: `0.2.0-experimental.14`; tag: `dev-14`; protocol: `2`; validation snapshot: compatible `v3`.
- BLE profile: `android-ble-lab-v1`; min RSSI samples `3`; fresh `5000 ms`; holdover/hard expiry `10000 ms`.
- Unfiltered recovery `10000 ms`; filtered probe public hard maximum `15000 ms`; internal exit target `14500 ms`.
- Restart cooldown `30000 ms`; maximum recovery attempts `3` per rolling 5 minutes.
- Geometry is automatic only. Manual geometry, human scanning, validated human localization and rescue claims remain false.
- Screenshots are not acceptance evidence. JSON/JSONL is the diagnostic source of truth.
- No calibration, path-loss, ranging, reciprocal fusion, holdover, sigma-aging or geometry-solver changes are authorized by dev14.

Schema decision: v3 is retained because it explicitly allows compatible additional properties. Dev14 adds recovery/lifecycle diagnostics without changing existing required semantics.
