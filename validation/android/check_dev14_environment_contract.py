#!/usr/bin/env python3
from pathlib import Path
import subprocess,sys
root=Path(__file__).resolve().parents[2]
n=(root/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt').read_text()
b=(root/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleAcquisitionPolicy.kt').read_text()
e=(root/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/EnvironmentStrategyValidator.kt').read_text()
v=(root/'apps/mobile/src/version.ts').read_text()
required=[
 ('version','0.2.0-experimental.14' in v and 'reportVersion: 16' in v and 'snapshotSchemaVersion: 3' in v),
 ('strict preflight','START_REQUIRES_FILTERED_PRIMARY' in n and 'preflight_at_start' in n),
 ('runtime authorized recovery','AUTHORIZED_BOUNDED_RECOVERY_GENERATION' in e and 'AUTHORIZED_FILTERED_RECOVERY_PROBE' in e),
 ('unauthorized rejected','UNFILTERED_RECOVERY_WITHOUT_GENERATION' in e and 'RECOVERY_GENERATION_MISMATCH' in e),
 ('env counters','authorized_strategy_transition_count' in n and 'unauthorized_strategy_violation_count' in n),
 ('generation provenance','strategyRecoveryGeneration' in b and 'strategy_recovery_generation' in b),
 ('old false rule removed','currentStrategy() != BleAcquisitionStrategy.FILTERED_PRIMARY) issues += "NOT_FILTERED_PRIMARY"' not in n),
]
for name,ok in required:
 print(f"{name}: {'PASS' if ok else 'FAIL'}")
 if not ok: sys.exit(1)
subprocess.run([sys.executable,str(root/'validation/analysis/validate_environment_authorization.py')],cwd=root,check=True)
print('dev14 environment contract: PASS')
