#!/usr/bin/env python3
"""Validate Body Finder protocol-v2 field exports against external ground truth.

Standard-library only. Ground-truth coordinates are read from a separate file and
are never part of the production solver. The validator aligns the solver's arbitrary
2-D gauge to the external frame using its anchor/axis and tries both mirror signs.
"""
import argparse, json, math
from pathlib import Path

def load_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None

def candidates_from_obj(obj, source):
    out=[]
    if not isinstance(obj,dict): return out
    if isinstance(obj.get('geometry'),dict): out.append((source,obj.get('geometry'),obj.get('estimate_array_frame'),obj))
    if isinstance(obj.get('estimate_array_frame'),dict) and isinstance(obj.get('geometry'),dict): pass
    if isinstance(obj.get('local'),dict) or isinstance(obj.get('peers'),list):
        g=obj.get('geometry')
        if isinstance(g,dict): out.append((source,g,obj.get('estimate_array_frame'),obj))
    return out

def read_candidates(directory):
    out=[]
    for p in sorted(directory.glob('*.json')):
        if p.name in {'ground-truth.json','validation-summary.json'}: continue
        obj=load_json(p)
        out.extend(candidates_from_obj(obj,p.name))
    for p in sorted(directory.glob('*.jsonl')):
        try:
            for i,line in enumerate(p.read_text(encoding='utf-8',errors='replace').splitlines()):
                try: obj=json.loads(line)
                except Exception: continue
                if isinstance(obj,dict) and isinstance(obj.get('geometry'),dict):
                    out.append((f'{p.name}:{i+1}',obj.get('geometry'),obj.get('human_estimate'),obj))
        except Exception: pass
    return out

def choose_candidate(xs):
    if not xs: return None
    def score(x):
        _,g,_,_=x
        state=g.get('state','')
        rank={'GEOMETRY_2D':4,'GEOMETRY_DEGRADED':3,'GEOMETRY_1D':2,'GEOMETRY_INSUFFICIENT':1}.get(state,0)
        return (rank,len(g.get('positions') or []),len(g.get('used_edges') or []),g.get('revision') or 0)
    return max(xs,key=score)

def dist(a,b): return math.hypot(a[0]-b[0],a[1]-b[1])
def rmse(xs): return math.sqrt(sum(x*x for x in xs)/len(xs)) if xs else None

def transform_factory(g,truth,sign):
    pm={p.get('node_id'):(float(p.get('x_m',0)),float(p.get('y_m',0))) for p in g.get('positions') or []}
    a=g.get('anchor_node_id'); b=g.get('axis_node_id')
    if not a or not b or a not in pm or b not in pm or a not in truth or b not in truth: return None
    ga,gb=pm[a],pm[b]; ta,tb=truth[a],truth[b]
    ev=(gb[0]-ga[0],gb[1]-ga[1]); tv=(tb[0]-ta[0],tb[1]-ta[1]); el=math.hypot(*ev); tl=math.hypot(*tv)
    if el<1e-9 or tl<1e-9: return None
    eu=(ev[0]/el,ev[1]/el); en=(-eu[1],eu[0]); tu=(tv[0]/tl,tv[1]/tl); tn=(-tu[1],tu[0])
    def f(p):
        dx=p[0]-ga[0]; dy=p[1]-ga[1]; x=dx*eu[0]+dy*eu[1]; y=dx*en[0]+dy*en[1]
        return (ta[0]+x*tu[0]+sign*y*tn[0], ta[1]+x*tu[1]+sign*y*tn[1])
    return f

def validate(directory,gt):
    xs=read_candidates(directory); chosen=choose_candidate(xs)
    result={'input_directory':str(directory),'candidate_count':len(xs),'protocol_versions':sorted({str(x[3].get('protocol_version') or x[3].get('node',{}).get('protocol_version') or '') for x in xs}), 'manual_geometry_override_violations':[]}
    for src,_,_,obj in xs:
        vals=[obj.get('manual_geometry_override'),obj.get('local',{}).get('manual_geometry_override') if isinstance(obj.get('local'),dict) else None,obj.get('node',{}).get('manual_geometry_override') if isinstance(obj.get('node'),dict) else None]
        if any(v is True for v in vals): result['manual_geometry_override_violations'].append(src)
    if not chosen:
        result['error']='No geometry solution found in JSON/JSONL inputs'; return result
    src,g,target,obj=chosen; result.update({'selected_source':src,'geometry_state':g.get('state'),'dimension':g.get('dimension'),'frame_id':g.get('frame_id'),'revision':g.get('revision'),'solved_nodes':len(g.get('positions') or []),'used_edges':len(g.get('used_edges') or []),'rejected_edges':len(g.get('rejected_edges') or []),'residual_rms_m':g.get('residual_rms_m'),'condition_score':g.get('condition_score')})
    tech=set()
    for _,_,_,o in xs:
        ranges=o.get('range_observations') or []
        if isinstance(o.get('node'),dict): ranges += o['node'].get('ranges') or []
        if isinstance(o.get('local'),dict): ranges += o['local'].get('ranges') or []
        for r in ranges:
            if isinstance(r,dict) and r.get('technology'): tech.add(r['technology'])
    result['range_technologies']=sorted(tech)
    truth_raw=gt.get('node_positions_m') or {}; truth={k:(float(v[0]),float(v[1])) for k,v in truth_raw.items() if isinstance(v,list) and len(v)>=2}
    pm={p.get('node_id'):(float(p.get('x_m',0)),float(p.get('y_m',0))) for p in g.get('positions') or []}; common=sorted(set(pm)&set(truth));result['ground_truth_common_nodes']=common
    if len(common)>=2:
        pair_errors=[]
        for i,a in enumerate(common):
            for b in common[i+1:]: pair_errors.append(dist(pm[a],pm[b])-dist(truth[a],truth[b]))
        result['pairwise_distance_rmse_m']=rmse(pair_errors);result['pairwise_distance_max_abs_error_m']=max((abs(x) for x in pair_errors),default=None)
    best=None
    for sign in (1,-1):
        f=transform_factory(g,truth,sign)
        if not f: continue
        errs=[]
        for n in common: errs.append(dist(f(pm[n]),truth[n]))
        score=rmse(errs)
        if best is None or (score is not None and score<best[0]): best=(score,sign,f,errs)
    if best:
        score,sign,f,errs=best;result['alignment_mirror_sign']=sign;result['node_position_rmse_m']=score;result['node_position_max_error_m']=max(errs) if errs else None
        person=gt.get('person_position_m')
        if isinstance(target,dict) and isinstance(person,list) and len(person)>=2 and target.get('x_m') is not None and target.get('y_m') is not None:
            t=f((float(target['x_m']),float(target['y_m'])));err=dist(t,(float(person[0]),float(person[1])));result['target_aligned_position_m']=[t[0],t[1]];result['target_error_m']=err;radius=target.get('error_radius_95_m');result['target_reported_error_radius_95_m']=radius;result['target_inside_reported_95_region']=bool(radius is not None and err<=float(radius))
    return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('directory',type=Path);ap.add_argument('--ground-truth',type=Path,required=True);ap.add_argument('--output',type=Path);args=ap.parse_args();gt=load_json(args.ground_truth)
    if not isinstance(gt,dict): raise SystemExit('Invalid ground-truth JSON')
    result=validate(args.directory,gt);text=json.dumps(result,indent=2,sort_keys=True);print(text)
    if args.output: args.output.write_text(text+'\n',encoding='utf-8')
if __name__=='__main__': main()
