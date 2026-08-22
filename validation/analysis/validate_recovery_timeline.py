#!/usr/bin/env python3
import json,sys
p=json.load(open(sys.argv[1],encoding='utf-8')); events=(p.get('validation_run') or p).get('events',[])
last_seq=-1; last_wall=-1; last_elapsed=-1; first={}; stalls=[]
for e in events:
    assert e['seq']>last_seq,'non-monotonic seq'; assert e['wall_ms']>=last_wall,'non-monotonic wall_ms'; assert e.get('elapsed_ms',e.get('elapsed_from_run_start_ms',0))>=last_elapsed,'non-monotonic elapsed_ms'
    last_seq=e['seq']; last_wall=e['wall_ms']; last_elapsed=e.get('elapsed_ms',e.get('elapsed_from_run_start_ms',0))
    if e['type']=='BF_COHORT_STALLED': assert e.get('cohort_health')=='BF_COHORT_STALLED'; stalls.append(e)
    if e['type']=='RECOVERY_REQUESTED': assert any(s['seq']<e['seq'] for s in stalls),'recovery request before stall'
    if e['type']=='FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY':
        g=e.get('recovery_generation'); first[g]=first.get(g,0)+1; assert first[g]<=1,'duplicate first callback'
print('PASS timeline')
