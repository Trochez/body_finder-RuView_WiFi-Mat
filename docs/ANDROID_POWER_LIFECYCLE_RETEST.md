# Body Finder experimental.5 — Android awake/screen-off lifecycle retest

Run this after the basic BLE calibration/proximity check proves all three devices can see each other.

Experimental.5 adds an Android connected-device foreground service, a partial CPU wake lock, high-performance Wi-Fi lock, multicast lock, BLE-scan stall recovery and per-run delta counters.

This test determines what can truthfully be claimed about 5-minute field-session stability.

## Preconditions

Use the same `dev-*` on:

- Pixel 10 Pro;
- Pixel 7 Pro;
- Lenovo TB-J606L.

Enable:

```text
Wi-Fi ON / same LAN
Bluetooth ON
Location ON on Lenovo/API30
```

Allow notification permission if Android asks. Verify a persistent **Body Finder – active field session** notification is visible while the fabric is running.

Do not enable human scanning for this test.

## L1 — awake foreground 5 minutes

On all three devices:

1. Open Body Finder.
2. Open Expert.
3. Confirm `foreground_service_state = RUNNING`.
4. Confirm `wake_lock_held`, `wifi_lock_held`, and `multicast_lock_held` are true where supported.
5. Tap **Start validation run** on all three within roughly 10 seconds.
6. Keep every screen ON and the application visible.
7. Do not move the devices.
8. Wait exactly **5 minutes**.
9. Tap **End validation run** on each device.
10. Export JSON on each device.

Save:

```text
lifecycle-awake/
  pixel10-awake.json
  pixel7-awake.json
  lenovo-awake.json
  pixel10-awake-radar.png
  pixel7-awake-radar.png
  lenovo-awake-radar.png
  expert-screenshots/
```

### Expected

Per run, not accumulated since application startup:

```text
peer_expire_delta = 0 ideal
all_peer_uptime_percent >= 90%
BLE evidence uptime >= 90% target
scan_restart_delta normally 0, but an automatic recovery without permanent peer loss is acceptable and must remain visible
```

`metric_range_uptime_percent` and `geometry_2d_uptime_percent` may legitimately be 0 in experimental.5 because BLE RSSI is intentionally `PROXIMITY_ONLY` until calibrated. Do not fail this lifecycle test merely because metric geometry is withheld.

## L2 — screen off 5 minutes

This is the key regression for the earlier T4 ambiguity.

1. Re-open/restart the app if needed.
2. Confirm all three peers are visible.
3. Start a **new validation run** on each device.
4. Turn the display OFF on all three devices using the normal power button. Do not force-stop the app.
5. Leave all three devices untouched for **5 minutes**.
6. Turn screens back on.
7. Wait up to 30 seconds for reacquisition.
8. Open Expert.
9. End each validation run.
10. Export JSON immediately.

Save:

```text
lifecycle-screen-off/
  pixel10-screenoff.json
  pixel7-screenoff.json
  lenovo-screenoff.json
  screenshots-after-unlock/
```

### What to inspect

```text
lifecycle_diagnostics.foreground_service_state
lifecycle_diagnostics.screen_state
lifecycle_diagnostics.power_save_mode
lifecycle_diagnostics.device_idle_mode
lifecycle_diagnostics.wake_lock_held
lifecycle_diagnostics.wifi_lock_held
lifecycle_diagnostics.multicast_lock_held

validation_run.peer_expire_delta
validation_run.address_rebind_delta
validation_run.scan_restart_delta
validation_run.all_peer_uptime_percent
validation_run.ble_evidence_uptime_percent

fabric_diagnostics.peer_count_active
ble_diagnostics.scan_state
ble_diagnostics.scan_restart_count
ble_diagnostics.rebind_events
```

### Acceptance target

For this experimental release the minimum truthfulness gate is:

- the app does not permanently die;
- foreground service remains active or reports an explicit failure;
- after unlock, peers and BLE evidence reacquire automatically without restarting the app;
- no stale BLE distance is fabricated during the outage/recovery;
- reacquisition occurs within 30 seconds after unlock.

A stricter field target is:

```text
all_peer_uptime_percent >= 80% during screen-off run
BLE evidence uptime >= 80%
peer expiry delta as low as possible and explained
```

If the OS/OEM prevents these targets, report the observed limitation instead of hiding it.

## L3 — single-device screen off

If L2 fails, isolate the source:

Run three 3-minute subtests, each time turning off only one screen:

```text
L3a Pixel 10 screen off; Pixel7/Lenovo awake
L3b Pixel 7 screen off; Pixel10/Lenovo awake
L3c Lenovo screen off; Pixel10/Pixel7 awake
```

Export all three reports after each subtest. This distinguishes transmitter/advertiser suspension from receiver/network suspension.

## Address-rebind evidence

Experimental.5 records each debounced rebind with:

```text
identity
previous_address_fingerprint
new_address_fingerprint
wall_ms
reason
```

The real Bluetooth MAC is never exported.

Return these events; they will determine whether the high counts seen in T4b were real address rotation or duplicate software rebinding.

## RangingManager Pixel 10

On Pixel 10 also capture:

```text
system_ranging.state
consecutive_failures
open_failure_count
close_failure_count
unexpected_failure_count
retry_in_ms
circuit_open_in_ms
```

It is acceptable for system ranging to remain unavailable. The required behavior is bounded retry/circuit breaking and no loss of independent BLE evidence.

## Evidence bundle required

Return one ZIP:

```text
body-finder-exp5-lifecycle.zip
  lifecycle-awake/
  lifecycle-screen-off/
  lifecycle-single-screen-off/    # only if L2 fails
  notes.txt
```

`notes.txt` should state:

- whether Android battery saver was enabled;
- whether any device was charging;
- whether notification permission was granted;
- whether any app was manually backgrounded or killed;
- approximate Wi-Fi router distance;
- any unexpected OS dialog.
