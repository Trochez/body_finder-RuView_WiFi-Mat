#!/usr/bin/env python3
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[2]
policy=(ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleAcquisitionPolicy.kt').read_text()
module=(ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt').read_text()
version=(ROOT/'apps/mobile/src/version.ts').read_text()
app_json=json.loads((ROOT/'apps/mobile/app.json').read_text())
profile=json.loads((ROOT/'calibration/ble-range-calibration-profiles.json').read_text())
for t in ['FILTERED_PRIMARY','UNFILTERED_RECOVERY','BF_COHORT_STALLED','GLOBAL_SCANNER_HEALTHY','COHORT_STALL_THRESHOLD_MS = 5_000L','RECOVERY_UNFILTERED_WINDOW_MS = 10_000L','FILTERED_PROBE_WINDOW_MS = 15_000L','MIN_RESTART_COOLDOWN_MS = 30_000L','MAX_RECOVERY_ATTEMPTS_PER_5MIN = 3','startFilteredScan','startUnfilteredRecoveryScan','recoveryAttemptCount','RECOVERY_SUPPRESSED_MAX_ATTEMPTS','recoveryGenerationCounter','activeRecoveryGeneration']:
    assert t in policy,t
for t in ['bodyFinderCohortHealth','maintainAdaptiveScanner','VALIDATION_ENVIRONMENT_INVALID','BATTERY_SAVER_ON','CompletedValidationRun','snapshot_frozen','MANUFACTURER_FILTERED','scanGeneration']:
    assert t in module,t
assert '0.2.0-experimental.12' in version
assert 'reportVersion: 14' in version
assert 'humanScanningEnabled: false' in version
assert app_json['expo']['android']['versionCode']==12
assert app_json['expo']['extra']['releaseIteration']=='experimental.12'
est=(ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleRangeEstimator.kt').read_text(); cont=(ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleContinuityPolicy.kt').read_text()
assert '-69.19' in est and '3.62' in est
assert 'FRESH_MS = 5_000L' in cont and 'HOLDOVER_MAX_MS = 10_000L' in cont and 'SIGMA_AGING_M_PER_S = 0.15' in cont
active=next(p for p in profile['profiles'] if p['profile_id']==profile['active_profile_id'])
assert active['profile_id']=='android-ble-lab-v1' and active['validated'] and active['physical_confidence']=='COARSE'
print('experimental.12 adaptive acquisition + validation integrity contract OK')
