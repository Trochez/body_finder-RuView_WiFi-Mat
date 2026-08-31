# TESTING DEV20.9

Safety: experimental only. `final_go=false` until independent G12. Screenshots are not required; JSON is authoritative.

## Install
1. Download `BodyFinder-dev20.9-universal.apk` and `SHA256SUMS.txt`; verify SHA-256.
2. Uninstall/clear prior Body Finder state on Pixel 10 Pro, Pixel 7 Pro and Lenovo TB-J606L. Install the same APK on all three.
3. Same LAN; Bluetooth ON; Battery Saver OFF; screens ON; app foreground; Lenovo Location ON when Android requires it.
4. Put devices in a fixed non-collinear triangle, preferably each pair within the validated 0.5–5.0 m BLE domain.

## G10 — 6 JSON
1. Open all three apps. Wait until every device shows exactly 2 current peers, range TX/RX >0, required-frame oversize=0, same coordinator/generation, no ghost member, and same coordinator geometry publication.
2. On the elected coordinator only, calibrate EMPTY; wait for the same calibration id/hash/generation/topology and ACK 3/3.
3. Start `SMOKE_CAL_EMPTY` on all three; keep fixed for **>=330000 ms**; End and export one JSON/device.
4. Do not recalibrate or move nodes. Start `HUMAN_MOVING`; run **>=330000 ms**; End and export one JSON/device.
5. Put exactly the six fresh JSON files in one directory and run:
```bash
unzip validators-dev20.9.zip -d validators-dev20.9
python3 validators-dev20.9/validation/analysis/validate_dev20_9_smoke.py evidence/*.json --output dev20.9-smoke-go-no-go.json
```
6. Continue only if exit=0 and `g10_go=true`. Any NO-GO: STOP and share the six JSON plus verdict.

## G11/G12
After G10 GO, execute two independent days × 9 scenarios × 3 devices = 54 fresh JSON, each >=330000 ms, then run `validate_dev20_9_campaign.py`. G12 is an independent review. Only `g10_go && g11_go && g12_go` may permit global `final_go=true`.
