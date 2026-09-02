#!/usr/bin/env python3
"""Strict dev-20.17 three-node PRE_RUN validator. JSON only; screenshots are ignored."""
from __future__ import annotations
import argparse,json,re,sys
from pathlib import Path
from typing import Any
HEX64=re.compile(r'^[0-9a-fA-F]{64}$')

def walk(o:Any):
    if isinstance(o,dict):
        yield o
        for v in o.values(): yield from walk(v)
    elif isinstance(o,list):
        for v in o: yield from walk(v)
def vals(o,*keys):
    wanted={k.lower() for k in keys};out=[]
    for d in walk(o):
        for k,v in d.items():
            if str(k).lower() in wanted: out.append(v)
    return out
def first(o,*keys,default=None):
    v=vals(o,*keys);return v[0] if v else default
def ai(v,d=-1):
    try:return int(v)
    except:return d
def ab(v):
    if isinstance(v,bool):return v
    if isinstance(v,(int,float)):return bool(v)
    return isinstance(v,str) and v.strip().lower() in {'true','1','yes','ready','go','pass','committed','commit','healthy','valid'}
def s(v):return '' if v is None else str(v).strip()
def load(p,errs):
    try:
        d=json.loads(p.read_text(encoding='utf-8'));assert isinstance(d,dict);return d
    except Exception as e:errs.append(f'INVALID_JSON:{p.name}:{e}');return {}
def empty_oversize(v):
    if v is None:return True
    if isinstance(v,dict):return all(ai(x,0)==0 for x in v.values())
    if isinstance(v,list):return len(v)==0
    return ai(v,0)==0

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('files',nargs='*');ap.add_argument('--output');ns=ap.parse_args(argv)
    ps=[Path(x) for x in ns.files];errs=[]
    if len(ps)!=3:errs.append(f'EXACTLY_3_FILES_REQUIRED:{len(ps)}')
    docs=[load(p,errs) for p in ps];nodes=[];tokens=[];cohorts=[]
    for p,d in zip(ps,docs):
        if not d:continue
        n=s(first(d,'node_id','local_node_id','device_node_id'));nodes.append(n)
        if not n:errs.append(f'NODE_ID_REQUIRED:{p.name}')
        aa=ai(first(d,'authority_ack_count','authority_ready_count','authority_ack')); 
        if aa!=3:errs.append(f'AUTHORITY_ACK_3_REQUIRED:{p.name}:{aa}')
        geom=s(first(d,'geometry_state','geometry','geometry_mode')).upper()
        if geom!='GEOMETRY_2D':errs.append(f'GEOMETRY_2D_REQUIRED:{p.name}:{geom}')
        ca=ai(first(d,'peer_ack_count','calibration_ack_count','calibration_ack_ready_count'))
        if ca!=3:errs.append(f'CALIBRATION_ACK_3_REQUIRED:{p.name}:{ca}')
        if not ab(first(d,'calibration_ack_symmetric')):errs.append(f'CALIBRATION_ACK_SYMMETRIC_REQUIRED:{p.name}')
        sa=ai(first(d,'scenario_ack_count','scenario_ready_count'))
        if sa!=3:errs.append(f'SCENARIO_ACK_3_REQUIRED:{p.name}:{sa}')
        strategy=s(first(d,'acquisition_strategy','ble_acquisition_strategy','strategy')).upper()
        if not strategy or strategy in {'FAILED_SAFE','RECOVERING','UNFILTERED_RECOVERY','FILTERED_RECOVERY_PROBE'}:errs.append(f'ACQUISITION_NOT_READY:{p.name}:{strategy}')
        failures=ai(first(d,'critical_control_failure_count','critical_control_failures'),0)
        if failures!=0:errs.append(f'CRITICAL_CONTROL_FAILURE:{p.name}:{failures}')
        ov=first(d,'oversize_control_key_counts','critical_control_oversize_counts','critical_control_oversize_count','critical_control_oversize')
        if not empty_oversize(ov):errs.append(f'CRITICAL_CONTROL_OVERSIZE:{p.name}:{ov!r}')
        rr=ai(first(d,'runstart_ready_count','run_start_ready_count','run_start_ack_count'))
        if rr!=3:errs.append(f'RUNSTART_READY_3_REQUIRED:{p.name}:{rr}')
        if not ab(first(d,'runstart_commit','run_start_commit','run_start_committed')):errs.append(f'RUNSTART_COMMIT_REQUIRED:{p.name}')
        token=s(first(d,'campaign_run_token','run_start_token'));tokens.append(token)
        if not token or not HEX64.fullmatch(token):errs.append(f'CAMPAIGN_RUN_TOKEN_SHA256_REQUIRED:{p.name}')
        cohort=first(d,'expected_cohort','cohort','cohort_node_ids');cohorts.append(tuple(sorted(map(str,cohort))) if isinstance(cohort,list) else ())
    unique={x for x in nodes if x}
    if len(unique)!=3:errs.append(f'EXACTLY_3_UNIQUE_NODES_REQUIRED:{len(unique)}')
    if len({x for x in tokens if x})!=1:errs.append('CAMPAIGN_RUN_TOKEN_MISMATCH')
    if len({x for x in cohorts if x})!=1:errs.append('COHORT_MISMATCH')
    out={'schema':'PreRunDev2017PhysicalValidationV1','release':'dev-20.17','files':len(ps),'unique_nodes':sorted(unique),'errors':errs,'pre_run':'GO' if not errs else 'NO_GO','pre_run_go':not errs,'screenshots_required':False,'next_step':'RUN_G10' if not errs else 'STOP_AND_SHARE_EXACTLY_3_PRE_RUN_JSON'}
    text=json.dumps(out,indent=2,sort_keys=True);print(text)
    if ns.output:Path(ns.output).write_text(text+'\n',encoding='utf-8')
    return 0 if not errs else 2
if __name__=='__main__':sys.exit(main())
