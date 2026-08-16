# dev release physical test — Android + Ubuntu + WSL/Windows

Use this only with a `dev-*` prerelease. This is an experimental validation build, not rescue equipment.

## What to download

From the latest GitHub prerelease:

- `body-finder-ruview-universal.apk` — install on 3–4 Android devices.
- `body-finder-node-linux-x86_64.tar.gz` — native Ubuntu and WSL2.
- `body-finder-node-windows-x86_64.zip` — Windows host, optional but recommended.
- `SHA256SUMS` — integrity check.

## Topology

All nodes must be on the **same local Wi-Fi/LAN**. Internet may be disabled after downloading.

Place devices around a safe test zone and measure their positions in meters relative to a chosen origin. Example only — use your real measurements:

```text
Ubuntu / AP origin  (0,0)
Android A           (-2,0)
Android B           ( 2,0)
Android C           ( 0,3)
Android D           ( 0,-3)   optional
```

Do not invent coordinates. Better geometry gives more meaningful results.

## 1 — Android: each of 3–4 devices

1. Install APK:
   `adb install -r body-finder-ruview-universal.apk`
   or copy/tap the APK on the phone.
2. Connect all phones to the same Wi-Fi.
3. Open **Body Finder – RuView** and grant requested nearby/Wi-Fi/location permissions.
4. In **Radar**, enter that phone's measured `x,y` position and tap **Set position**.
5. Keep the target area EMPTY. Tap **Calibrate empty scene** and do not move devices.
6. After calibration, tap **Start scan**.
7. Confirm the node count rises as other phones/Ubuntu appear.
8. Open **Expert** and confirm the local RSSI value changes over time and `CSI` is not falsely shown as working.

## 2 — Native Ubuntu

Extract and run:

```bash
tar xzf body-finder-node-linux-x86_64.tar.gz
chmod +x body-finder-node
./body-finder-node --node ubuntu-native --x 0 --y 0 --calibrate 10 --record ubuntu-native.jsonl
```

Keep the test area empty during the first 10 seconds.

Expected: one JSON line/second; `peer_count` should increase when Android nodes are discovered. If Wi-Fi RSSI is accessible, `node.rssi_dbm` is numeric. If not, it must be `null`/probe-failed — never synthetic.

## 3 — WSL2

Inside WSL:

```bash
tar xzf body-finder-node-linux-x86_64.tar.gz
chmod +x body-finder-node
./body-finder-node --node wsl --x 4 --y 4 --calibrate 10 --record wsl.jsonl
```

Expected: WSL may report no RF interface. That is acceptable. It must identify platform `wsl` and must not invent RSSI/CSI.

If multicast/broadcast does not cross WSL networking, also run the Windows native node below; WSL networking failure is data we need, not a reason to fake a peer.

## 4 — Windows host

PowerShell:

```powershell
Expand-Archive body-finder-node-windows-x86_64.zip -DestinationPath .\body-finder-win
cd .\body-finder-win
.\body-finder-node.exe --node windows-host --x 4 --y 0 --calibrate 10 --record windows-host.jsonl
```

The node converts Windows' real WLAN percentage from `netsh` to an approximate dBm-like value and marks the source in capabilities. If there is no active WLAN interface, RSSI remains unavailable.

## 5 — Empty-scene control

With all nodes scanning and nobody in the target zone:

- record **60 seconds**;
- take screenshots of Radar and Expert;
- on every Android tap **Share result JSON** and save/share the text as `android-<device>.json`.

A stable empty scene should not be treated as a validated human. Any `POSSIBLE_HUMAN` in this period is a false-positive candidate that must be reported.

## 6 — One-person LOS test

Without moving sensors:

1. Put one person at a measured ground-truth coordinate, e.g. `(0,1.5)` — record the actual value.
2. Stay mostly still for 60 s.
3. Then move gently within ~1 m for 30 s.
4. Save Android result JSON again and keep Ubuntu/Windows JSONL recording.
5. Record the true `(x,y)` and approximate time range.

## 7 — One-wall test

Only after LOS:

1. Keep sensor positions fixed.
2. Put the person at a known coordinate behind one stable wall.
3. Record wall material and approximate thickness.
4. Empty baseline 30 s, then person present 60 s.
5. Export the same results.

Do **not** use an unstable structure or real collapse hazard.

## 8 — Node removal/failover

During a live scan:

1. Close Body Finder on one Android; peer count should drop within ~5 s.
2. Restart it; peer count should recover.
3. Stop the current highest-score coordinator (normally native Ubuntu). Another node should become the deterministic coordinator; capture the result.

## Return these results for verification

Send back one ZIP containing:

```text
android-pixel7pro-empty.json
android-pixel7pro-person.json
android-pixel10pro-empty.json
android-pixel10pro-person.json
android-lenovo-empty.json
android-lenovo-person.json
android-4-*.json                 # if used
ubuntu-native.jsonl
wsl.jsonl
windows-host.jsonl              # if used
ground-truth.txt
screenshots/
```

`ground-truth.txt` should contain only:

```text
Test area dimensions: W x H meters
Node coordinates: name=(x,y), ...
AP/hotspot coordinate if known: (x,y) or unknown
Empty interval: local time start/end
LOS person coordinate: (x,y)
LOS interval: local time start/end
Wall person coordinate: (x,y)
Wall interval: local time start/end
Wall material/thickness: ...
Anything moved during test: yes/no + what
```

## What will be verified from your returned data

1. APK launches across different Android models/API levels.
2. Capability probes are truthful.
3. Android↔Android↔Ubuntu/Windows discovery works and WSL limitations are identified.
4. Coordinator election/hot-add/remove behaves deterministically.
5. RSSI samples are live and not synthetic.
6. Empty-scene false positives.
7. RSSI distribution shift empty→person.
8. Whether the estimated position changes toward ground truth more than chance/baseline.
9. Actual localization error, MAE/RMSE where enough trials exist.
10. Whether reported 95% uncertainty covers the true position.
11. Whether the wall case contains usable signal or must remain `PRESENCE-ONLY/FAILED`.

Do not interpret a negative scan as proof that no human is present.
