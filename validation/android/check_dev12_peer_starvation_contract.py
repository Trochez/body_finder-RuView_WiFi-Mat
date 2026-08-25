from pathlib import Path
root=Path(__file__).resolve().parents[2]
pol=(root/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleAcquisitionPolicy.kt').read_text()
mod=(root/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt').read_text()
app=(root/'apps/mobile/App.tsx').read_text(); ver=(root/'apps/mobile/src/version.ts').read_text()
need=[('PEER_STARVATION_PERSIST_MS = 6_000L',pol),('RecoveryTriggerKind.PEER_STARVATION',mod),('recoveryCallbackEligible',mod),('acceptance_duration_eligible',mod),('FLAG_KEEP_SCREEN_ON',mod),('screenshots_required',app),('0.2.0-experimental.12',ver)]
missing=[x for x,s in need if x not in s]; assert not missing,missing
frozen=[('MIN_SAMPLES_FOR_RANGE = 3',mod),('RANGE_FRESHNESS_MS = 5_000L',mod),('MIN_RESTART_COOLDOWN_MS = 30_000L',pol),('MAX_RECOVERY_ATTEMPTS_PER_5MIN = 3',pol)]
missing=[x for x,s in frozen if x not in s]; assert not missing,missing
print('PASS dev12 peer starvation/static truth contract')
