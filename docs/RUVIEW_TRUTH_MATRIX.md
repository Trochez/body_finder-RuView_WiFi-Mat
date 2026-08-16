# RuView Truth Matrix

Reviewed upstream: `ruvnet/RuView@4685618388a5e49fad5b3005806f3bdd6a7c25c3`.

| Component / claim | Body Finder classification | Current use |
|---|---|---|
| `wifi-densepose-hardware` parsers/adapters | REAL_BUT_UNVALIDATED_HERE | Adapter boundary only; no local CSI hardware proven |
| `wifi-densepose-signal` CSI processing | REAL_BUT_UNVALIDATED_HERE | Not used for RSSI path |
| `wifi-densepose-mat` domain/detection/localization crate | REAL_BUT_UNVALIDATED_HERE | Semantics/reference; physical disaster performance not inherited |
| `wifi-densepose-wifiscan` commodity Wi-Fi concepts | REAL_BUT_UNVALIDATED_HERE | Architectural reference; Body Finder has independent baseline |
| RuView mobile UI | REAL_BUT_UNVALIDATED_HERE | Design reference only; Body Finder owns its mobile app |
| General phone CSI | UNSUPPORTED | Never assumed; requires verified adapter |
| Through-wall human localization on current lab | UNVALIDATED | Must be established by returned ground-truth recordings |
| Breathing/heartbeat on common RSSI-only devices | UNSUPPORTED | UI must report unavailable |
| Simulated/demo streams | SIMULATED | Never allowed to satisfy physical gates |

## Promotion rule

A physical sensing capability can move to `VERIFIED_REAL` only when source code, executable path, device probe, recording, and ground-truth result are all available. Upstream performance numbers are not Body Finder product claims.
