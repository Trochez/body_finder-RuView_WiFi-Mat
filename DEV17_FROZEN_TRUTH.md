# DEV17 Frozen Truth

Release: `dev-17` / build `0.2.0-experimental.17`.

`dev-17` is tooling/release-only. Protocol `2` and completed validation snapshot schema `v4` remain frozen. No behavior change is permitted in BLE acquisition, estimator, continuity/holdover, calibration, reciprocal fusion, autogeometry, UDP, Android ranging coexistence/yield, or recovery state machine.

Frozen values: profile `android-ble-lab-v1`; RSSI@1m `-69.19 dBm`; path-loss exponent `3.62`; domain `0.5–5.0 m`; fresh `5000 ms`; holdover/hard expiry `10000 ms`; unfiltered action/hard `9500/10000 ms`; filtered probe action/observed/hard `14000/14500/15000 ms`; recovery budget `3 / rolling 300000 ms`; restart cooldown `30000 ms`; RangingManager BLE yield `120000 ms`; manual geometry `false`; screenshots `false`.

CI gate: every diff from tag `dev-16` under runtime source/calibration paths must be empty, except release metadata (`apps/mobile/src/version.ts`, `apps/mobile/app.json`). Any other runtime diff makes the release fail.
