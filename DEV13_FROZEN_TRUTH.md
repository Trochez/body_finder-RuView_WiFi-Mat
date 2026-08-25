# dev-13 frozen truth

Protocol remains 2. BLE physics remain unchanged: profile `android-ble-lab-v1`; RSSI@1m=-69.19 dBm; n=3.62; domain=0.5–5.0 m; minSamples=3; fresh=5000 ms; holdover/hard-expiry=10000 ms; sigma aging=0.15 m/s; peer starvation=6000 ms; cohort stall=5000 ms; recovery<=3/rolling 5 min; cooldown=30000 ms; API36 BLE yield=120000 ms; automatic geometry and reciprocal fusion unchanged.

Startup requires FILTERED_PRIMARY + MANUFACTURER_FILTERED + hardware_filter_count>0. Runtime UNFILTERED_RECOVERY/FILTERED_RECOVERY_PROBE is valid only with matching bounded recovery-generation provenance. Human scanning/localization/rescue remain disabled. Acceptance evidence is JSON-only; screenshots are not required.
