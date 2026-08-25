#!/usr/bin/env python3
import json,sys,math
# usage: script export1 export2 export3 ground-truth.json
exports=[json.load(open(x,encoding='utf-8')) for x in sys.argv[1:-1]]; gt=json.load(open(sys.argv[-1],encoding='utf-8'))
truth=gt.get('pairs',gt)
obs=[]
for p in exports:
    r=p.get('validation_run') or p
    for o in r.get('fused_range_observations_at_end',[]):
        a=o.get('from_node_id') or o.get('source_node_id'); b=o.get('to_node_id') or o.get('target_node_id'); d=o.get('distance_m')
        if a and b and isinstance(d,(int,float)): obs.append((a,b,float(d)))
errors=[]
for item in truth if isinstance(truth,list) else []:
    a=item.get('a'); b=item.get('b'); d=float(item['distance_m']); vals=[x[2] for x in obs if {x[0],x[1]}=={a,b}]
    if vals: errors.append(abs(sum(vals)/len(vals)-d))
out={'physical_confidence':'COARSE','directional_mae_m':sum(errors)/len(errors) if errors else None,'reciprocal_fused_mae_m':sum(errors)/len(errors) if errors else None,'maximum_absolute_error_m':max(errors) if errors else None,'uncertainty_coverage':None,'recalibration_gate':False}
print(json.dumps(out,indent=2))
