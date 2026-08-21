#!/usr/bin/env python3
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[2]
policy=(ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleAcquisitionPolicy.kt').read_text()
module=(ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt').read_text()
app=(ROOT/'apps/mobile/App.tsx').read_text()
profile=json.loads((ROOT/'calibration/ble-range-calibration-profiles.json').read_text())
assert 'FILTERED_PRIMARY' in policy
assert 'UNFILTERED_RECOVERY' in policy
assert 'BF_COHORT_STALLED' in policy
assert 'GLOBAL_SCANNER_HEALTHY' in policy
assert 'COHORT_STALL_THRESHOLD_MS = 5_000L' in policy
assert 'MIN_RESTART_COOLDOWN_MS = 30_000L' in policy
assert 'MAX_RECOVERY_ATTEMPTS_PER_5MIN = 3' in policy
assert 'startFilteredScan' in policy and 'startUnfilteredRecoveryScan' in policy
assert 'bodyFinderCohortHealth' in module
assert 'maintainAdaptiveScanner' in module
assert 'VALIDATION_ENVIRONMENT_INVALID' in module
assert 'BATTERY_SAVER_ON' in module
assert '0.2.0-experimental.9' in app
assert 'HUMAN_SCANNING_ENABLED = false' in app
# frozen truth guards
assert '-69.19' in (ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleRangeEstimator.kt').read_text()
assert '3.62' in (ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleRangeEstimator.kt').read_text()
cont=(ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleContinuityPolicy.kt').read_text()
assert 'FRESH_MS = 5_000L' in cont and 'HOLDOVER_MAX_MS = 10_000L' in cont and 'SIGMA_AGING_M_PER_S = 0.15' in cont
print('experimental.9 adaptive acquisition contract OK')
