#!/usr/bin/env python3
import json,sys
r=json.load(open(sys.argv[1])).get('validation_run',{})
ev=r.get('events',[]); ok=True; errs=[]
for key in ('seq','wall_ms','elapsed_from_run_start_ms'):
 vals=[e.get(key,0) for e in ev]
 if vals!=sorted(vals): ok=False; errs.append('non_monotonic_'+key)
by={}
for e in ev:
 g=e.get('recovery_generation')
 if g is None: continue
 by.setdefault(g,[]).append(e)
for g,es in by.items():
 req=[e for e in es if e.get('type')=='RECOVERY_REQUESTED']; first=[e for e in es if e.get('type')=='FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY']; term=[e for e in es if e.get('type') in ('RECOVERY_SUCCESS','RECOVERY_FAILURE')]
 if len(req)>1 or len(first)>1 or len(term)>1: ok=False; errs.append(f'exactly_once_generation_{g}')
 if req and term and req[0].get('seq',0)>term[0].get('seq',0): ok=False; errs.append(f'causal_inversion_{g}')
 if req and req[0].get('trigger_kind')=='PEER_STARVATION' and first and first[0].get('peer_id')!=req[0].get('trigger_peer_id'): ok=False; errs.append(f'wrong_target_first_valid_{g}')
print(json.dumps({'pass':ok,'errors':errs,'generation_count':len(by)},indent=2)); sys.exit(0 if ok else 1)
