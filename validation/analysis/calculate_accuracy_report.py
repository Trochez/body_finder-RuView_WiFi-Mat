#!/usr/bin/env python3
import argparse,json,math
ap=argparse.ArgumentParser(); ap.add_argument('--ground-truth',required=True); ap.add_argument('--export',action='append',required=True); a=ap.parse_args()
gt=json.load(open(a.ground_truth)); obs=[]
for f in a.export:
 d=json.load(open(f)); obs += d.get('fused_range_observations',[])
pairs={}
for o in obs:
 p=tuple(sorted([o.get('observer_node_id',''),o.get('peer_node_id','')]))
 if all(p) and isinstance(o.get('distance_m'),(int,float)): pairs.setdefault('|'.join(p),[]).append(float(o['distance_m']))
errs=[]
for k,t in gt.get('pairs_m',{}).items():
 vals=pairs.get(k,[])
 if vals: errs.append(sum(vals)/len(vals)-float(t))
out={'physical_confidence':'COARSE','pair_count':len(errs),'directional_mae_m':sum(abs(x) for x in errs)/len(errs) if errs else None,'maximum_absolute_error_m':max(map(abs,errs)) if errs else None,'note':'informative; not a dev-12 blocker'}
print(json.dumps(out,indent=2))
