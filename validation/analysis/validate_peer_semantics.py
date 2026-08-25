#!/usr/bin/env python3
import json,sys
r=json.load(open(sys.argv[1])).get('validation_run',{}); peers=r.get('per_peer',r.get('per_peer_at_end',[])); ok=True; errs=[]
for p in peers:
 if p.get('run_starvation_recovery_success_count',0)>p.get('run_starvation_recovery_participation_count',0): ok=False; errs.append(p.get('node_id','?')+':success_gt_participation')
 if p.get('run_starvation_recovery_failure_count',0)>p.get('run_starvation_recovery_participation_count',0): ok=False; errs.append(p.get('node_id','?')+':failure_gt_participation')
print(json.dumps({'pass':ok,'peer_count':len(peers),'errors':errs},indent=2)); sys.exit(0 if ok else 1)
