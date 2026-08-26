#!/usr/bin/env python3
from pathlib import Path
root=Path(__file__).resolve().parents[2]
base=root/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative'
policy=(base/'BleAcquisitionPolicy.kt').read_text(); continuity=(base/'BleContinuityPolicy.kt').read_text(); native=(base/'BodyFinderNativeModule.kt').read_text()
for token in ('RECOVERY_UNFILTERED_WINDOW_MS = 10_000L','FILTERED_PROBE_WINDOW_MS = 15_000L','FILTERED_PROBE_EXIT_TARGET_MS = 14_500L','MIN_RESTART_COOLDOWN_MS = 30_000L','MAX_RECOVERY_ATTEMPTS_PER_5MIN = 3'):
    assert token in policy,token
for token in ('FRESH_MS = 5_000L','HOLDOVER_MAX_MS = 10_000L','HARD_EXPIRY_MS = 10_000L'):
    assert token in continuity,token
for token in ('MIN_SAMPLES_FOR_RANGE = 3','recovery_first_valid_callback_delta','run_first_callback_after_recovery_count'):
    assert token in native,token
# Directed dev15 smoke uses two phones, therefore each phone has exactly one remote BLE peer.
assert 'if (expectedKnownPeerCount() < 1) issues += "EXPECTED_BLE_PEERS_LT_1"' in native
assert '.put("expected_ble_peers_ready", expectedKnownPeerCount() >= 1)' in native
assert 'EXPECTED_BLE_PEERS_LT_2' not in native
print('DEV15_FROZEN_TRUTH_AND_TELEMETRY_CONTRACT_PASS')
