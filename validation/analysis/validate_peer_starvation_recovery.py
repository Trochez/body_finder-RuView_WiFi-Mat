#!/usr/bin/env python3
import json,sys
r=json.load(open(sys.argv[1])).get('validation_run',{}); ev=r.get('events',[]); ok=True; errs=[]
req=[e for e in ev if e.get('type')=='RECOVERY_REQUESTED' and e.get('trigger_kind')=='PEER_STARVATION']
for q in req:
 g=q.get('recovery_generation'); peer=q.get('trigger_peer_id') or q.get('peer_id'); ge=[e for e in ev if e.get('recovery_generation')==g]
 first=[e for e in ge if e.get('type')=='FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY']
 suc=[e for e in ge if e.get('type')=='RECOVERY_SUCCESS']
 if suc and (not first or first[0].get('peer_id')!=peer): ok=False; errs.append(f'generation {g}: success_without_target_first_valid')
 if len(suc)>1 or len([e for e in ge if e.get('type')=='RECOVERY_FAILURE'])>1: ok=False; errs.append(f'generation {g}: duplicate_terminal')
 if q.get('trigger_kind')!='PEER_STARVATION': ok=False
print(json.dumps({'pass':ok,'peer_starvation_recovery_requests':len(req),'errors':errs},indent=2)); sys.exit(0 if ok else 1)
