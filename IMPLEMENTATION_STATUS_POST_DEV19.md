# Post-dev19 implementation status

`dev-20` is the first executable milestone of the post-dev19 program. The software includes a self-contained Android BLE-RSSI evidence timeline, deterministic HUMAN/NO-HUMAN/INDETERMINATE baselines, leakage-safe campaign tooling, RTI localization with mandatory covariance/withholding, conservative tracking/cluster semantics, capability-truth validation, controlled NLOS validation, and an aggregate fail-closed v1 gate.

The release does **not** claim physical human detection/localization/NLOS/rescue validation before the new campaigns are run. `humanLocalizationValidated=false` and `rescueUseValidated=false` remain hard safety flags. Later milestone validators are shipped now so the same self-contained JSON corpus can be evaluated without screenshots.
