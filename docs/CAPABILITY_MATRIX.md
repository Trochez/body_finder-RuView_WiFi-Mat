# Capability Matrix

This file contains **expectations**, not fake physical results. The app/node must populate actual states at runtime.

| Device | Initial role | Wi-Fi RSSI | RTT | BLE | CSI | Fabric |
|---|---|---|---|---|---|---|
| Pixel 7 Pro | sensor/display | PROBE_AT_RUNTIME | PROBE_AT_RUNTIME | PROBE_AT_RUNTIME | UNSUPPORTED unless verified plugin | PROBE_AT_RUNTIME |
| Pixel 10 Pro | sensor/display | PROBE_AT_RUNTIME | PROBE_AT_RUNTIME | PROBE_AT_RUNTIME | UNSUPPORTED unless verified plugin | PROBE_AT_RUNTIME |
| Lenovo Tab2 | sensor/display/legacy candidate | PROBE_AT_RUNTIME | PROBE_AT_RUNTIME | PROBE_AT_RUNTIME | UNSUPPORTED unless verified plugin | PROBE_AT_RUNTIME |
| Native Ubuntu | coordinator/sensor/recorder | PROBE_AT_RUNTIME | adapter dependent | PROBE_AT_RUNTIME | PROBE_AT_RUNTIME | PROBE_AT_RUNTIME |
| WSL | compute/development | usually PROBE_FAILED unless interface is exposed | adapter dependent | adapter dependent | UNSUPPORTED until proven | PROBE_AT_RUNTIME |
| Windows host | compute/node | PROBE_AT_RUNTIME via `netsh` | not implemented in exp.1 | not human evidence in exp.1 | UNSUPPORTED | PROBE_AT_RUNTIME |

Runtime states are `WORKING`, `WORKING_DEGRADED`, `SUPPORTED_UNVERIFIED`, `UNSUPPORTED`, `PERMISSION_REQUIRED`, `PROBE_FAILED`.

**Rule:** API/feature presence alone is not `WORKING`. In experimental.1, Android RTT and BLE hardware presence are reported `SUPPORTED_UNVERIFIED` until a real ranging/scan path is exercised.
