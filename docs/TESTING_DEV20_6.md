# TESTING DEV-20.6

Evidence is JSON only; screenshots are neither required nor accepted.

1. Install `BodyFinder-dev20.6-universal.apk` on Pixel 10 Pro, Pixel 7 Pro and Lenovo TB-J606L. Wi-Fi/Bluetooth/Location ON; Battery Saver OFF; screen ON; app foreground; clean session.
2. Wait on all three for exactly 2 peers, logical cohort=3 and `FILTERED_PRIMARY`.
3. Start EMPTY calibration only on the elected coordinator. Continue only when all three show identical calibration id/hash/generation/topology/coordinator generation, ACK 3/3 and `distributed_calibration_ready=true`.
4. `SMOKE_CAL_EMPTY`: 90–120 s, no person/no node movement; export one JSON/device.
5. Without moving nodes or recalibrating, `HUMAN_MOVING`: 90–120 s with a person moving through the area; export one JSON/device.
6. Validate on Linux/WSL: `unzip validators-dev20.6.zip -d validators-dev20.6 && python3 validators-dev20.6/validation/analysis/validate_dev20_6_smoke.py --detector ./body-finder-detector-linux-x86_64 ./evidence/*.json`.
7. Windows: `Expand-Archive validators-dev20.6.zip validators-dev20.6`; then `py validators-dev20.6\validation\analysis\validate_dev20_6_smoke.py --detector .\body-finder-detector-windows-x86_64.exe .\evidence\*.json`.
8. GO only if exit=0 and `final_go=true`. Otherwise stop; do not run the 54-JSON campaign.
9. Send the six JSON plus validator report for diagnosis. No screenshot/log bundle is needed for the primary diagnosis.

After smoke GO: two independent days × 9 scenarios × 3 devices = 54 fresh JSON, >=330 s/scenario. No code/parameter/schema/protocol change after freeze. `human_localization_validated=false`; `rescue_use_validated=false`.
