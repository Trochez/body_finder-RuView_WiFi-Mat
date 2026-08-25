#!/usr/bin/env python3
import json,sys
p=json.load(open(sys.argv[1])); r=p.get('validation_run',p); ev=r.get('events',[])
req={}
terminal={}
errors=[]
for e in ev:
 g=e.get('recovery_generation'); t=e.get('type')
 if t=='RECOVERY_REQUESTED' and e.get('trigger_kind')=='PEER_STARVATION': req[g]=e.get('peer_id')
 if t=='FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY' and g in req and e.get('peer_id')!=req[g]: errors.append(f'generation {g}: first valid from wrong peer')
 if t in ('RECOVERY_SUCCESS','RECOVERY_FAILURE'):
  if g in terminal: errors.append(f'generation {g}: duplicate terminal')
  terminal[g]=t
for g,peer in req.items():
 if g not in terminal: errors.append(f'generation {g}: missing terminal')
print(json.dumps({'validator':'peer_starvation_recovery','peer_recovery_generations':len(req),'errors':errors,'pass':not errors},indent=2)); sys.exit(0 if not errors else 2)
