from pathlib import Path
r=Path(__file__).resolve().parents[2]
p=(r/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/PeerStarvationRecovery.kt').read_text()
m=(r/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt').read_text()
a=(r/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleAcquisitionPolicy.kt').read_text()
v=(r/'apps/mobile/src/version.ts').read_text()
for x in ['PERSISTENCE_MS=6_000L','PEER_STARVED','FULL_COHORT_STALL','PEER_STARVATION']: assert x in p
for x in ['peerStarvationCandidate','targetRecoverySatisfied','FLAG_KEEP_SCREEN_ON','acceptance_duration_eligible']: assert x in m
for x in ['lastRecoveryTriggerPeerId','noteValidCallback','peer_starvation_recovery_request_count']: assert x in a
assert "0.2.0-experimental.12" in v and 'reportVersion: 14' in v
# frozen physical truth remains untouched
br=(r/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleRangeEstimator.kt').read_text(); bc=(r/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleContinuityPolicy.kt').read_text()
assert '-69.19' in br and '3.62' in br and 'MIN_SAMPLES_FOR_RANGE = 3' in m and '10_000L' in bc
print('PASS dev12 contract')
