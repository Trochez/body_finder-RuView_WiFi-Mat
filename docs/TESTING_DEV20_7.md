# TESTING DEV-20.7

JSON is authoritative; screenshots are not required.

1. Install `BodyFinder-dev20.7-universal.apk` on Pixel 10 Pro, Pixel 7 Pro and Lenovo TB-J606L. Enable Wi-Fi/Bluetooth/Location; Battery Saver OFF; screens ON; apps foreground.
2. Start a clean session. Wait for exactly two peers/device and logical cohort=3.
3. Start EMPTY calibration only on the elected coordinator. Continue only after identical calibration id/hash/generation/topology and ACK 3/3 on all three.
4. `SMOKE_CAL_EMPTY`: 90-120 s, nobody in the area and no node movement; export one JSON/device.
5. Without recalibration/node movement, `HUMAN_MOVING`: 90-120 s with one person moving through the area; export one JSON/device.
6. Linux/WSL: `unzip validators-dev20.7.zip -d validators-dev20.7 && python3 validators-dev20.7/validation/analysis/validate_dev20_7_smoke.py --detector ./body-finder-detector-linux-x86_64 ./evidence/*.json`.
7. Windows: `Expand-Archive validators-dev20.7.zip validators-dev20.7`; `py validators-dev20.7\validation\analysis\validate_dev20_7_smoke.py --detector .\body-finder-detector-windows-x86_64.exe .\evidence\*.json`.
8. GO only with exit=0 and `final_go=true`. Any failure: STOP and share the six JSON plus `dev20.7-smoke-go-no-go.json`.
9. Only after smoke GO: on two different calendar days run all 9 scenarios on all 3 devices, each >=330 s (54 fresh JSON total). Linux/WSL: `python3 validators-dev20.7/validation/analysis/validate_dev20_7_campaign.py --detector ./body-finder-detector-linux-x86_64 ./campaign/*.json`; Windows: `py validators-dev20.7\validation\analysis\validate_dev20_7_campaign.py --detector .\body-finder-detector-windows-x86_64.exe .\campaign\*.json`. GO only with exit=0 and `final_go=true`.
