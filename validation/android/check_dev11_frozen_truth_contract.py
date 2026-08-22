#!/usr/bin/env python3
import json, pathlib, sys
ROOT=pathlib.Path(__file__).resolve().parents[2]

import re
profile=json.load(open(ROOT/'calibration/ble-range-calibration-profiles.json'))
text=json.dumps(profile)
assert 'android-ble-lab-v1' in text and '-69.19' in text and '3.62' in text
cont=(ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleContinuityPolicy.kt').read_text()
pol=(ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleAcquisitionPolicy.kt').read_text()
for x in ['FRESH_MS = 5_000L','HOLDOVER_MAX_MS = 10_000L','SIGMA_AGING_M_PER_S = 0.15']: assert x in cont,x
for x in ['COHORT_STALL_THRESHOLD_MS = 5_000L','RECOVERY_UNFILTERED_WINDOW_MS = 10_000L','FILTERED_PROBE_WINDOW_MS = 15_000L','MIN_RESTART_COOLDOWN_MS = 30_000L','MAX_RECOVERY_ATTEMPTS_PER_5MIN = 3','SYSTEM_RANGING_BLE_YIELD_MS = 120_000L']: assert x in pol,x
core=(ROOT/'crates/body-finder-core/src/lib.rs').read_text(); assert 'pub const PROTOCOL_VERSION: u16 = 2;' in core
print('PASS dev11 frozen truth contract')
