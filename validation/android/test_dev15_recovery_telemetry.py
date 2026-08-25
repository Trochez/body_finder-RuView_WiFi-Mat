#!/usr/bin/env python3
from __future__ import annotations
import copy, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'validation/analysis'))
from dev15_validation import _recovery_analysis
base=json.load(open(ROOT/'validation/fixtures/dev15/campaign/pixel-10-pro-long-1.json',encoding='utf-8'))['validation_run']

def analyze(run): return _recovery_analysis(run)[0]
def assert_has(run, code):
    errors=analyze(run); assert any(code in e for e in errors),(code,errors)

# 1 recovery success
assert analyze(copy.deepcopy(base)) == []
# 2 recovery failure (no FIRST_VALID, one failure terminal)
f=copy.deepcopy(base); f['events']=[e for e in f['events'] if e['type']!='FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY']; terminal=next(e for e in f['events'] if e['type']=='RECOVERY_SUCCESS'); terminal['type']='RECOVERY_FAILURE'
assert analyze(f) == []
# 3 wrong peer callback
x=copy.deepcopy(base); next(e for e in x['events'] if e['type']=='FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY')['peer_id']='wrong-peer'; assert_has(x,'FIRST_VALID_WRONG_TARGET')
# 4 duplicate callback
x=copy.deepcopy(base); first=next(e for e in x['events'] if e['type']=='FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY'); dup=copy.deepcopy(first); dup['seq']=first['seq']+1; dup['wall_ms']=first['wall_ms']+100; x['events'].insert(3,dup)
for i,e in enumerate(x['events'],1): e['seq']=i
assert_has(x,'RECOVERY_FIRST_VALID_COUNT_INVALID')
# 5 callback after terminal
x=copy.deepcopy(base); first=next(e for e in x['events'] if e['type']=='FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY'); terminal=next(e for e in x['events'] if e['type']=='RECOVERY_SUCCESS'); first['seq'],terminal['seq']=terminal['seq'],first['seq']; first['wall_ms'],terminal['wall_ms']=terminal['wall_ms']+1,first['wall_ms']; x['events']=sorted(x['events'],key=lambda e:e['seq']); assert_has(x,'CALLBACK_AFTER_TERMINAL')
# 6 two independent generations
x=copy.deepcopy(base); original=copy.deepcopy(x['events']); second=[]
for e in original:
    y=copy.deepcopy(e); y['seq']+=len(original); y['wall_ms']+=30000; y['elapsed_ms']+=30000; y['elapsed_from_run_start_ms']+=30000; y['recovery_generation']=2; second.append(y)
x['events']=original+second; errors,totals,peers=_recovery_analysis(x); assert errors==[],errors; assert totals['peer_request']==2 and totals['first']==2
# missing FIRST_VALID
x=copy.deepcopy(base); x['events']=[e for e in x['events'] if e['type']!='FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY']; assert_has(x,'RECOVERY_FIRST_VALID_COUNT_INVALID')
# duplicate terminal
x=copy.deepcopy(base); t=copy.deepcopy(next(e for e in x['events'] if e['type']=='RECOVERY_SUCCESS')); t['seq']+=1; t['wall_ms']+=1; x['events'].insert(4,t); x['events']=sorted(x['events'],key=lambda e:e['wall_ms']); [e.__setitem__('seq',i) for i,e in enumerate(x['events'],1)]; assert_has(x,'RECOVERY_TERMINAL_COUNT_INVALID')
# budget exceeded: four valid generations inside 5 minutes
x=copy.deepcopy(base); all_events=[]
for g in range(1,5):
    for e in original:
        y=copy.deepcopy(e); off=(g-1)*30000; y['seq']=len(all_events)+1; y['wall_ms']+=off; y['elapsed_ms']+=off; y['elapsed_from_run_start_ms']+=off; y['recovery_generation']=g; all_events.append(y)
x['events']=all_events; assert_has(x,'RECOVERY_BUDGET_EXCEEDED')
# hard probe expiry
x=copy.deepcopy(base); start=next(e for e in x['events'] if e.get('to_strategy')=='FILTERED_RECOVERY_PROBE'); end=next(e for e in x['events'] if e.get('from_strategy')=='FILTERED_RECOVERY_PROBE'); end['wall_ms']=start['wall_ms']+15001; assert_has(x,'FILTERED_PROBE_HARD_LIMIT_EXCEEDED')
print('DEV15_RECOVERY_TELEMETRY_MATRIX_PASS')
