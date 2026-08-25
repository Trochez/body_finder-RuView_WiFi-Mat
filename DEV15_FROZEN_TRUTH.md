# DEV15 FROZEN TRUTH

Release `dev-15` / build `0.2.0-experimental.15`.

**NO BLE/RANGING/FUSION/GEOMETRY RETUNING.** Dev15 changes are telemetry, evidence metadata, validators, reporting, documentation and release hygiene only.

| Contract | Frozen value |
|---|---:|
| BLE profile | `android-ble-lab-v1` |
| min RSSI samples | `3` |
| fresh | `5000 ms` |
| holdover max | `10000 ms` |
| hard expiry | `10000 ms` |
| recovery unfiltered window | `10000 ms` |
| filtered recovery probe hard max | `15000 ms` |
| filtered recovery exit target | `14500 ms` |
| restart cooldown | `30000 ms` |
| max recovery attempts / 5 min | `3` |
| protocol | `2` |
| validation snapshot schema | `v3` |
| manual geometry | `false` |
| automatic geometry | `true` |
| screenshots | `false` |
| human scanning | `false` |
| human localization validated | `false` |
| rescue use validated | `false` |

RSSI@1m, path-loss exponent, calibration profile, range estimator, reciprocal fusion, holdover/sigma aging, peer expiry, autogeometry, coordinator publication and API36 coexistence/yield semantics remain frozen from dev14.
