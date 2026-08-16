# Quick physical test — dev release

> Experimental validation only. A negative scan does not prove that nobody is present.

## 1. Install

Download the latest `dev-*` GitHub prerelease.

- Modern Android: `body-finder-ruview-universal.apk`
- Old Android that cannot install it: `body-finder-ruview-legacy-minsdk21.apk`
- Native Ubuntu + WSL2: `body-finder-node-linux-x86_64.tar.gz`
- Windows host: `body-finder-node-windows-x86_64.zip`

Put every device on the same local Wi-Fi/LAN.

## 2. Place and calibrate 3–4 Androids

Measure each device position in meters in one shared coordinate system, for example only: A=(-2,0), B=(2,0), C=(0,3), D=(0,-3). Use your real measurements.

On each full Android app:
1. Open app and allow requested Location/Nearby Wi-Fi permission.
2. Enter that device's measured `x,y` and tap **Set position**.
3. Keep the test area empty and tap **Calibrate empty scene**.
4. Tap **Start scan**.

On the legacy APK, perform the equivalent **SET MEASURED POSITION → CALIBRATE → START SCAN** steps. It is a sensor node only; use a modern Android for Radar.

## 3. Start the recorder on native Ubuntu

```bash
tar xzf body-finder-node-linux-x86_64.tar.gz
chmod +x body-finder-node
./body-finder-node --node ubuntu-native --x 0 --y 0 --calibrate 10 --record ubuntu-native.jsonl
```

Keep the area empty during the 10-second Ubuntu calibration. Leave this process running for the entire test; its `all_nodes` field records the Android peer evidence each second.

## 4. WSL and Windows

WSL2:

```bash
./body-finder-node --node wsl --x 4 --y 4 --calibrate 10 --record wsl.jsonl
```

Windows PowerShell, optional but recommended:

```powershell
.\body-finder-node.exe --node windows-host --x 4 --y 0 --calibrate 10 --record windows-host.jsonl
```

It is acceptable for WSL to report no RF interface. It must not invent RSSI or CSI.

## 5. Run three controlled scenarios without moving sensors

- **EMPTY:** nobody in the target area for 60 seconds.
- **LOS:** one person at a measured `(x,y)` for 60 seconds; then move gently within ~1 m for 30 seconds.
- **WALL:** the same person at a measured `(x,y)` behind one safe stable wall for 60 seconds. Record material and approximate thickness.

At the end of each scenario, on each modern Android tap **Share result JSON**. On a legacy Android use **SHARE SNAPSHOT JSON** if convenient.

## 6. Return one ZIP

Include:

```text
ubuntu-native.jsonl
wsl.jsonl
windows-host.jsonl        # if used
android-*.json             # exported snapshots
ground-truth.txt
screenshots/               # Radar + Expert from one modern Android per scenario
```

`ground-truth.txt`:

```text
Test area: W x H meters
Nodes: name=(x,y), name=(x,y), ...
EMPTY local time: start - end
LOS person=(x,y), local time: start - end
WALL person=(x,y), local time: start - end
Wall: material, approximate thickness
Anything moved except the person: yes/no; details
```

From that bundle we can verify device discovery/failover, real RSSI, false positives, empty→person signal shift, actual position error/MAE/RMSE, whether the reported 95% uncertainty covers ground truth, and whether the wall case provides useful evidence at all.
