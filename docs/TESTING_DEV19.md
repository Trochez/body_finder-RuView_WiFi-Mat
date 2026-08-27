# TESTING DEV19 — Pixel 10 peer continuity gate

`dev-19 / 0.2.0-experimental.19` hardens acquisition/peer continuity. It does **not** enable human detection/localization/rescue. Screenshots are neither required nor accepted as primary evidence; the exported JSON is self-contained.

## 1. Verify and install

Download every asset from release `dev-19`, then verify:

```bash
sha256sum -c SHA256SUMS.txt
```

Install **the same** `BodyFinder-dev19-universal.apk` on:

- Pixel 10 Pro (Android API 37)
- Pixel 7 Pro
- Lenovo TB-J606L

The APK may be downloaded directly on each Android and opened from Downloads; USB is not required.

## 2. Physical setup

Before opening the LONG run, confirm on all 3 devices:

- same LAN / Wi-Fi fabric;
- Bluetooth ON and permissions granted;
- Battery Saver OFF;
- screen ON;
- Body Finder foreground;
- foreground service `RUNNING`;
- Lenovo Location ON;
- devices stationary in a non-collinear triangle;
- pair distances inside the frozen calibrated BLE domain, **0.5–5.0 m**;
- same session/fabric on all nodes.

Do not move or background any device during the run.

## 3. Warm-up and preflight

1. Open the app on all three devices.
2. Wait **at least 30 s** for discovery.
3. On each device confirm preflight is ready and shows exactly **2 expected peers**.
4. If any node shows fewer than 2, do not start; fix connectivity/permissions first.

## 4. Single final 3-Android campaign

1. Start a **LONG validation run** on all three devices as close together as practical.
2. Keep all three stationary/foreground for **at least 330 s**.
3. End each run.
4. Use **Share complete test JSON** once per device.
5. Save exactly:
   - `pixel10-dev19-final.json`
   - `pixel7-dev19-final.json`
   - `lenovo-dev19-final.json`

No screenshots are needed.

## 5. Validate the three exports

```bash
unzip validators-dev19.zip -d validators-dev19
python3 validators-dev19/validation/analysis/validate_dev19_session.py \
  pixel10-dev19-final.json \
  pixel7-dev19-final.json \
  lenovo-dev19-final.json \
  --output dev19-3android-acceptance.json
```

Expected: top-level `"pass": true` and every gate PASS on every node. In particular:

```text
build                                  = 0.2.0-experimental.19
protocol_version                       = 2
snapshot_schema_version                = 4
expected_peer_count_at_start           = 2
expected_peer_ids_at_start             = 2 unique IDs
environment_valid                      = true
environment_violation_count            = 0
elapsed_ms                             >= 330000
peer_expire_delta                      = 0
usable_metric_range_uptime_percent     >= 90
geometry_2d_uptime_percent             >= 90
recovery_attempts_max_in_rolling_5min  <= 3
hard timing breaches                   = 0
end strategy                           = FILTERED_PRIMARY
active_recovery_generation             = null
PEER_EXPIRED event count               = peer_expire_delta
human_scanning_enabled                 = false
human_localization_validated           = false
rescue_use_validated                   = false
```

`fabric_event_timeline` must be present and self-consistent. `PEER_BECAME_STALE` followed by `PEER_REACTIVATED` is diagnostic and may occur; **any `PEER_EXPIRED` makes G4 fail**.

## 6. Pixel 10 diagnostic A/B only if final gate fails

Do **not** change calibration, reciprocal fusion, geometry, or UDP timeout ad hoc. Preserve the failing JSON first. The exported fabric timeline already includes UDP gap, last RX, scanner generation, ranging state, BLE sample age, network state and lifecycle state around each transition. Use that evidence to decide the next controlled A/B; do not blame `RangingManager` merely because API 37 supports it.

## 7. Ubuntu closure

Reuse the existing `empty-01` native Ubuntu capture; do not recapture solely for dev19. Run replay twice and require the same `deterministic_digest`:

```bash
chmod +x body-finder-replay-linux-x86_64 body-finder-validate-session-linux-x86_64
./body-finder-validate-session-linux-x86_64 --manifest empty-01.manifest.json --input empty-01.jsonl > empty-01.validation-dev19.json
./body-finder-replay-linux-x86_64 --input empty-01.jsonl > empty-01.replay-dev19-a.json
./body-finder-replay-linux-x86_64 --input empty-01.jsonl > empty-01.replay-dev19-b.json
```

The two digests must match.

## 8. Windows closure

Use `body-finder-windows-x86_64.zip` for native Windows recorder/replay/validation. Existing functional Windows evidence remains valid. If native validator execution is blocked by Device Guard, record that as an **environment policy restriction**, not an algorithm failure; replay/measurement evidence remains separately evaluated.

## 9. Evidence to return

Return only the three Android JSON files plus `dev19-3android-acceptance.json` (and Ubuntu/Windows JSON only if revalidated). Once all three Androids PASS, acquisition is unblocked for the subsequent human/no-human work; until then all three human/rescue flags remain false.
