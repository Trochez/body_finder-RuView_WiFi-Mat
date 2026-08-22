#!/usr/bin/env python3
import json, pathlib, sys
ROOT=pathlib.Path(__file__).resolve().parents[2]

def errors(events):
    out=[]
    for a,b in zip(events,events[1:]):
        if b.get('seq',0)<=a.get('seq',0): out.append('seq')
        if b.get('wall_ms',0)<a.get('wall_ms',0): out.append('wall_ms')
        if b.get('elapsed_ms',0)<a.get('elapsed_ms',0): out.append('elapsed_ms')
    first={}
    stalls=[]
    requests=[]
    for e in events:
        if e.get('type')=='BF_COHORT_STALLED':
            stalls.append(e)
            if e.get('cohort_health')!='BF_COHORT_STALLED': out.append('stall_state')
        if e.get('type')=='RECOVERY_REQUESTED': requests.append(e)
        if e.get('type')=='FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY':
            g=e.get('recovery_generation'); first[g]=first.get(g,0)+1
    if any(v>1 for v in first.values()): out.append('duplicate_first')
    for req in requests:
        if not any(s.get('seq',0)<req.get('seq',0) and s.get('wall_ms',0)<=req.get('wall_ms',0) for s in stalls): out.append('request_before_stall')
    return out
valid=json.load(open(ROOT/'validation/fixtures/dev11/timeline-valid.json'))['events']
assert not errors(valid), errors(valid)
for name,expected in [('timeline-timestamp-inversion.json','wall_ms'),('stalled-event-wrong-state.json','stall_state'),('duplicate-first-callback.json','duplicate_first')]:
    assert expected in errors(json.load(open(ROOT/'validation/fixtures/dev11'/name))['events'])
src=(ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/ValidationEventLog.kt').read_text()
policy=(ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleAcquisitionPolicy.kt').read_text()
assert 'firstCallbackRecordedGeneration' in src and 'recovery_generation' in src
assert 'cohortHealth = next' in policy and 'activeRecoveryGeneration' in policy
print('PASS recovery timeline contract')
