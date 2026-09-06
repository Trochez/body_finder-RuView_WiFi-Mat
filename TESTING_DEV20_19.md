# TESTING dev-20.19

JSON-only evidence. **No screenshots.** G10 stays `PHYSICAL_PENDING/NO_GO` until the final command below returns `g10_go=true`.

## 0. Verify download

Download all `dev-20.19` prerelease assets, then:

```bash
sha256sum -c SHA256SUMS.txt
python3 validate_dev20_19_prerun.py --help >/dev/null
python3 validate_dev20_19_g10.py --help >/dev/null
```

Use **`BodyFinder-dev20.19-universal.apk`** for all three phones.

## 1. Clean install on exactly 3 Android devices

For each device:

```bash
adb -s <SERIAL> uninstall com.trochez.bodyfinderruview || true
adb -s <SERIAL> install BodyFinder-dev20.19-universal.apk
adb -s <SERIAL> shell monkey -p com.trochez.bodyfinderruview -c android.intent.category.LAUNCHER 1
```

Keep all three apps foregrounded and on the same test network/session. Do not mix dev-20.18 and dev-20.19.

## 2. PRE_RUN

1. Wait until every phone shows **Peers 2/2**, **Authority 3/3**, and **GEOMETRY_2D**.
2. On the elected coordinator only, tap **Calibrar escena vacía** once. Keep the area empty.
3. Wait until all three show the same current calibration ID/hash/generation/topology/binding, local artifact `PROMOTED`, **Calibration ACK 3/3**, and distributed calibration ready.
4. On coordinator issue `SMOKE_CAL_EMPTY`; wait **Scenario ACK 3/3**.
5. Start validation on coordinator; wait **RunStart READY 3/3 + COMMIT** on all three.
6. Before running 330 s, use **Exportar diagnóstico** on each phone. Save exactly three files.
7. Validate:

```bash
python3 validate_dev20_19_prerun.py \
  pre-run-diagnostic-dev20.19-<PHONE1>.json \
  pre-run-diagnostic-dev20.19-<PHONE2>.json \
  pre-run-diagnostic-dev20.19-<PHONE3>.json \
  --output prerun-verdict.json
```

If it returns non-zero or `pre_run_go=false`: **STOP** and share the three PRE_RUN JSONs only. Do not spend 330 s on acceptance.

## 3. EMPTY acceptance

Only after PRE_RUN GO:

1. Keep scene empty and devices fixed.
2. Run `SMOKE_CAL_EMPTY` for **>=330 s**.
3. Coordinator initiates Freeze; wait **Freeze READY 3/3 + COMMIT**.
4. Export one acceptance JSON from each phone. Keep all three.

## 4. HUMAN_MOVING acceptance

Without moving devices and **without recalibrating**:

1. Coordinator issues `HUMAN_MOVING`; wait Scenario 3/3.
2. Start a **fresh RunStart** and verify READY 3/3 + COMMIT.
3. Move one human through the target area for **>=330 s**.
4. Freeze 3/3 + COMMIT.
5. Export one JSON from each phone.

You now have exactly six acceptance JSONs: 3 EMPTY + 3 HUMAN_MOVING.

## 5. Official G10

```bash
python3 validate_dev20_19_g10.py \
  empty-phone1.json empty-phone2.json empty-phone3.json \
  human-phone1.json human-phone2.json human-phone3.json \
  --output g10-verdict.json
```

Only `g10_go=true` means:

```text
g10=GO
g11=UNBLOCKED
dev21=UNBLOCKED
final_go=true
```

Any other result remains fail-closed.

## Optional desktop artifact smoke

Linux:

```bash
tar -xzf body-finder-node-linux-x86_64.tar.gz
./body-finder-node --help
./body-finder-detector-linux-x86_64 --help
```

Windows/WSL:

```powershell
Expand-Archive body-finder-windows-wsl-x86_64.zip -DestinationPath dev20.19-win
.\body-finder-detector-windows-x86_64.exe --help
```

## What to send back

- If PRE_RUN fails: the **3 PRE_RUN JSONs + `prerun-verdict.json`**.
- If PRE_RUN passes: the **6 acceptance JSONs + `g10-verdict.json`**.
- Screenshots are unnecessary.
