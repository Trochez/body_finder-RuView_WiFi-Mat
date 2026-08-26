#!/usr/bin/env python3
import argparse, json, pathlib, sys

def main():
    p=argparse.ArgumentParser();p.add_argument('--manifest',required=True);p.add_argument('--measurements',required=True);p.add_argument('--output');a=p.parse_args()
    m=json.load(open(a.manifest,encoding='utf-8')); errors=[]; rows=[]
    if m.get('schema_version')!=1: errors.append('manifest schema_version != 1')
    policy=m.get('evidence_policy',{})
    if policy.get('screenshots_required') is not False: errors.append('screenshots_required must be false')
    if policy.get('json_self_contained') is not True: errors.append('json_self_contained must be true')
    if policy.get('simulation_is_physical_proof') is not False: errors.append('simulation cannot be physical proof')
    last={}
    for i,line in enumerate(open(a.measurements,encoding='utf-8'),1):
        if not line.strip(): continue
        try:r=json.loads(line)
        except Exception as e: errors.append(f'line {i}: invalid json: {e}');continue
        rows.append(r)
        if r.get('schema_version')!=1: errors.append(f'line {i}: schema_version != 1')
        if r.get('session_id')!=m.get('session_id'): errors.append(f'line {i}: session mismatch')
        key=(r.get('source_node_id'),r.get('peer_or_bssid'),r.get('modality')); ts=r.get('timestamp_monotonic_ns')
        if not isinstance(ts,int) or ts<0: errors.append(f'line {i}: invalid timestamp');continue
        if key in last and ts<last[key]: errors.append(f'line {i}: non-monotonic timestamp for {key}')
        last[key]=ts
        if not r.get('capability_provenance'): errors.append(f'line {i}: missing provenance')
    if not rows: errors.append('no measurements')
    report={'schema_version':1,'gate':'dev18_session_integrity','pass':not errors,'measurement_count':len(rows),'error_count':len(errors),'errors':errors,'session_id':m.get('session_id'),'physical_acceptance_claimed':False}
    text=json.dumps(report,indent=2)+'\n';print(text,end='')
    if a.output:pathlib.Path(a.output).write_text(text,encoding='utf-8')
    return 0 if not errors else 2
if __name__=='__main__':sys.exit(main())
