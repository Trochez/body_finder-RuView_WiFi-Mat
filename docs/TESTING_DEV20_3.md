# TESTING DEV-20.3

Status: **prerelease; physical acceptance PENDING; dev-21 BLOCKED**. Screenshots are not required.

## 1. Verify release
Download all assets and run `sha256sum -c SHA256SUMS.txt` (Linux/WSL). Install **BodyFinder-dev20.3-universal.apk** on Pixel 10 Pro, Pixel 7 Pro and Lenovo TB-J606L. Confirm build `0.2.0-experimental.20.3` and the same detector parameter hash on all three.

## 2. Mandatory 3-device smoke (do this before long tests)
Place the 3 devices as a fixed non-collinear triangle. Wi-Fi/Bluetooth ON, Battery Saver OFF, screens ON, app foreground. Confirm every node sees the other two. Run 30–60 s EMPTY and 30–60 s HUMAN_MOVING, concurrently on all 3, then share the 6 JSON files. GO only if healthy windows show 3 nodes / 6 directional links / 3 baselines, all peers export the same coordinator decision ID/version/hash, offline replay matches exactly, and loss of a node/link becomes INDETERMINATE rather than NO_HUMAN.

## 3. Final fresh TEST — only after smoke GO
For **Day 1**, run each scenario concurrently on all 3 devices for >=330 s (target ~360 s): `EMPTY_CAL`, `EMPTY_TEST`, `HUMAN_STATIONARY_CENTER`, `HUMAN_MOVING`, `HUMAN_NEAR_LENOVO`, `HUMAN_NEAR_PIXEL10`, `HUMAN_NEAR_PIXEL7`, `HUMAN_OUTSIDE`, `NON_HUMAN_MOTION`. For NON_HUMAN_MOTION record the actual moving non-human object/action in the external manifest. Repeat all nine on **Day 2** with a new independent EMPTY_CAL. Do not move devices within a scenario and do not change code/parameters after freeze.

Expected: **54 fresh JSON** (9 x 2 x 3), no screenshots.

## 4. Validate
Unzip `validators-dev20.3.zip`; build campaign-v3 from the 54 JSON plus external truth, then run the dev20.3 validator. Required GO: recall>=0.90, specificity>=0.85, healthy indeterminate<=0.10, stationary recall>=0.80, moving recall>=0.90, all calibration/acquisition/environment gates PASS, online/offline parity PASS, peer authoritative consistency PASS, localization/rescue flags false. Any failure => NO-GO and dev-21 remains blocked.
