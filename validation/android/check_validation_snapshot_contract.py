#!/usr/bin/env python3
from pathlib import Path
r=Path(__file__).resolve().parents[2]; n=(r/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt').read_text()
for t in ['completedSnapshotJson','snapshot_frozen','recovery_attempt_delta','restart_suppressed_delta','ranging_yield_transition_delta','acquisition_state_at_end','event_timeline_total_count']: assert t in n,t
assert 'completedSnapshotJson?.let { JSONObject(it) }' in n
print('validation snapshot contract: PASS')
