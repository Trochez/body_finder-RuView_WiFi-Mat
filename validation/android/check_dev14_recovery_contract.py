#!/usr/bin/env python3
from pathlib import Path
r=Path(__file__).resolve().parents[2]
b=(r/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleAcquisitionPolicy.kt').read_text()
n=(r/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt').read_text()
e=(r/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/EnvironmentViolationTracker.kt').read_text()
required=['FILTERED_PROBE_WINDOW_MS = 15_000L','FILTERED_PROBE_EXIT_TARGET_MS = 14_500L','RECOVERY_UNFILTERED_WINDOW_MS = 10_000L','MIN_RESTART_COOLDOWN_MS = 30_000L','MAX_RECOVERY_ATTEMPTS_PER_5MIN = 3','noteRecoveryFirstValidCallback','firstValidCallbackGeneration != generation','transition(BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE, now, "RECOVERY_SUCCESS")','transition(BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE, now, "RECOVERY_FAILURE")']
missing=[x for x in required if x not in b]
missing += [x for x in ['FILTERED_PROBE_EXIT_TARGET_MS','noteRecoveryFirstValidCallback(now, callbackPeerId)','EnvironmentViolationTracker.observe','snapshot_identity_sha256'] if x not in n]
missing += [x for x in ['total_background_ms','max_background_interval_ms','foreground_transition_count','confirmed','ACTIVITY_LIFECYCLE'] if x not in e]
assert not missing, missing
print('dev14 recovery/lifecycle contract PASS')
