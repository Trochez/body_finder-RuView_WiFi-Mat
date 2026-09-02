#!/usr/bin/env python3
"""Strict dev-20.17 G10 physical validator. No screenshots are consumed."""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from pathlib import Path
from typing import Any
MIN_DURATION_MS=330_000;MAX_PRIMARY_AGE_MS=5_000;MAX_RESTARTS_PER_330S=6
HEX64=re.compile(r'^[0-9a-fA-F]{64}$')

def walk(obj:Any):
    if isinstance(obj,dict):
        yield obj
        for v in obj.values():yield from walk(v)
    elif isinstance(obj,list):
        for v in obj:yield from walk(v)
def vals(obj:Any,*keys:str):
    wanted={k.lower() for k in keys};out=[]
    for d in walk(obj):
        for k,v in d.items():
            if str(k).lower() in wanted:out.append(v)
    return out
def first(obj:Any,*keys:str,default=None):
    v=vals(obj,*keys);return v[0] if v else default
def as_int(v,default=-1):
    try:return int(v)
    except:return default
def as_bool(v):
    if isinstance(v,bool):return v
    if isinstance(v,(int,float)):return bool(v)
    return isinstance(v,str) and v.strip().lower() in {'true','1','yes','ready','go','pass','committed','commit','healthy','valid'}
def norm_s(v):return '' if v is None else str(v).strip()
def empty_oversize(v):
    if v is None:return True
    if isinstance(v,dict):return all(as_int(x,0)==0 for x in v.values())
    if isinstance(v,list):return len(v)==0
    return as_int(v,0)==0
def req_count(d,aliases,expected,label,name,errs):
    v=first(d,*aliases);n=as_int(v)
    if n!=expected:errs.append(f'{label}_REQUIRED_{expected}:{name}:actual={v!r}')
def req_commit(d,aliases,label,name,errs):
    v=first(d,*aliases)
    if not as_bool(v):errs.append(f'{label}_COMMIT_REQUIRED:{name}:actual={v!r}')
def load(path,errs):
    try:
        d=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(d,dict):raise ValueError('root must be object')
        return d
    except Exception as e:errs.append(f'INVALID_JSON:{path.name}:{e}');return {}

def main(argv=None):
    ap=argparse.ArgumentParser(description='Validate exactly six dev-20.17 physical G10 JSONs');ap.add_argument('files',nargs='*');ap.add_argument('--output');ns=ap.parse_args(argv)
    paths=[Path(x) for x in ns.files];errs=[]
    if len(paths)!=6:errs.append(f'EXACTLY_6_FILES_REQUIRED:{len(paths)}')
    rows=[load(p,errs) for p in paths]
    scenarios=[];node_ids=[];sessions=[];cohorts=[];tokens=[]
    cal_ids=[];cal_hashes=[];cal_gens=[];topo_hashes=[];coord_ids=[];coord_gens=[];authority_digests=[]
    for p,d in zip(paths,rows):
        name=p.name
        if not d:continue
        if first(d,'acceptance_eligible','physical_acceptance_eligible') is False:errs.append(f'PRE_RUN_NOT_ACCEPTANCE:{name}')
        if norm_s(first(d,'evidence_phase','capture_phase','run_phase')).upper()=='PRE_RUN':errs.append(f'PRE_RUN_NOT_ACCEPTANCE:{name}')
        duration=as_int(first(d,'duration_ms','run_duration_ms','elapsed_ms'),0)
        if duration<MIN_DURATION_MS:errs.append(f'DURATION_LT_{MIN_DURATION_MS}:{name}:{duration}')
        scenario=norm_s(first(d,'scenario','scenario_id','scenario_name','validation_scenario'));scenarios.append(scenario)
        node=norm_s(first(d,'node_id','local_node_id','device_node_id'));node_ids.append(node)
        if not node:errs.append(f'NODE_ID_REQUIRED:{name}')
        session=norm_s(first(d,'session_id','validation_session_id'));sessions.append(session)
        if not session:errs.append(f'SESSION_ID_REQUIRED:{name}')
        cohort=first(d,'expected_cohort','cohort','cohort_node_ids');cohorts.append(tuple(sorted(map(str,cohort))) if isinstance(cohort,list) else ())
        req_count(d,('authority_ack_count','authority_ready_count','authority_ack'),3,'AUTHORITY_ACK',name,errs)
        geometry=norm_s(first(d,'geometry_state','geometry','geometry_mode')).upper()
        if geometry!='GEOMETRY_2D':errs.append(f'GEOMETRY_2D_REQUIRED:{name}:actual={geometry!r}')
        cid=norm_s(first(d,'calibration_id'));ch=norm_s(first(d,'calibration_hash'));cg=as_int(first(d,'calibration_generation'));th=norm_s(first(d,'topology_hash'));coord=norm_s(first(d,'coordinator_node_id','coordinator_id'));cgen=as_int(first(d,'coordinator_generation'));ad=norm_s(first(d,'authority_digest','authority_view_digest'))
        cal_ids.append(cid);cal_hashes.append(ch);cal_gens.append(cg);topo_hashes.append(th);coord_ids.append(coord);coord_gens.append(cgen);authority_digests.append(ad)
        for label,value in [('CALIBRATION_ID',cid),('CALIBRATION_HASH',ch),('TOPOLOGY_HASH',th),('COORDINATOR_ID',coord),('AUTHORITY_DIGEST',ad)]:
            if not value:errs.append(f'{label}_REQUIRED:{name}')
        if cg<0:errs.append(f'CALIBRATION_GENERATION_REQUIRED:{name}')
        if cgen<0:errs.append(f'COORDINATOR_GENERATION_REQUIRED:{name}')
        if th and not HEX64.fullmatch(th):errs.append(f'TOPOLOGY_HASH_NOT_SHA256:{name}')
        fp=norm_s(first(d,'topology_fingerprint'))
        if fp and th:
            once=hashlib.sha256(fp.encode()).hexdigest();twice=hashlib.sha256(once.encode()).hexdigest()
            if th==twice:errs.append(f'DOUBLE_HASH_EVIDENCE_REJECTED:{name}')
            if th!=once:errs.append(f'TOPOLOGY_HASH_NOT_CANONICAL_FROM_FINGERPRINT:{name}')
        req_count(d,('peer_ack_count','calibration_ack_count','calibration_ack_ready_count'),3,'CALIBRATION_ACK',name,errs)
        if not as_bool(first(d,'calibration_ack_symmetric')):errs.append(f'CALIBRATION_ACK_NOT_SYMMETRIC:{name}')
        matrices=vals(d,'peer_ack_matrix')
        if matrices and isinstance(matrices[0],list):
            m=matrices[0]
            if len(m)!=3 or any(not as_bool(x.get('acknowledged')) for x in m if isinstance(x,dict)):errs.append(f'CALIBRATION_ACK_SET_NOT_3_OF_3:{name}')
            observed=[norm_s(x.get('observed_topology_hash')) for x in m if isinstance(x,dict) and x.get('observed_topology_hash')]
            if observed and (len(observed)!=3 or len(set(observed))!=1 or (th and observed[0]!=th)):errs.append(f'CALIBRATION_ACK_TOPOLOGY_ASYMMETRY:{name}')
            if any(isinstance(x,dict) and x.get('rejection_reason') for x in m):errs.append(f'CALIBRATION_ACK_REJECTION_PRESENT:{name}')
        strategy=norm_s(first(d,'acquisition_strategy','ble_acquisition_strategy','strategy')).upper()
        if not strategy:errs.append(f'ACQUISITION_STRATEGY_REQUIRED:{name}')
        if strategy in {'FAILED_SAFE','RECOVERING','UNFILTERED_RECOVERY','FILTERED_RECOVERY_PROBE'}:errs.append(f'ACQUISITION_NOT_READY:{name}:{strategy}')
        if as_bool(first(d,'recovery_budget_exhausted','acquisition_recovery_budget_exhausted')):errs.append(f'RECOVERY_BUDGET_EXHAUSTED:{name}')
        remaining=first(d,'acquisition_recovery_budget_remaining','recovery_budget_remaining')
        if remaining is not None and as_int(remaining)<0:errs.append(f'INVALID_RECOVERY_BUDGET:{name}:{remaining!r}')
        if as_bool(first(d,'restart_storm_detected','scanner_restart_storm')):errs.append(f'SCANNER_RESTART_STORM:{name}')
        restart_delta=first(d,'scanner_restart_delta','filtered_scanner_restart_count_delta','scanner_restart_count_delta')
        if restart_delta is not None and as_int(restart_delta)>MAX_RESTARTS_PER_330S:errs.append(f'SCANNER_RESTART_STORM:{name}:delta={restart_delta}')
        primary_age=first(d,'last_successful_primary_observation_age_ms','primary_observation_age_ms','primary_metric_age_ms')
        if primary_age is None:errs.append(f'PRIMARY_OBSERVATION_AGE_REQUIRED:{name}')
        elif as_int(primary_age)>MAX_PRIMARY_AGE_MS:errs.append(f'STALE_PRIMARY_METRIC:{name}:{primary_age}')
        req_count(d,('scenario_ack_count','scenario_ready_count'),3,'SCENARIO_ACK',name,errs)
        req_count(d,('runstart_ready_count','run_start_ready_count','run_start_ack_count'),3,'RUNSTART_READY',name,errs)
        req_commit(d,('runstart_commit','run_start_commit','run_start_committed'),'RUNSTART',name,errs)
        token=norm_s(first(d,'campaign_run_token','run_start_token'));tokens.append(token)
        if not token or not HEX64.fullmatch(token):errs.append(f'CAMPAIGN_RUN_TOKEN_SHA256_REQUIRED:{name}')
        req_count(d,('freeze_ready_count','snapshot_ready_count','freeze_ack_count'),3,'FREEZE_READY',name,errs)
        req_commit(d,('freeze_commit','snapshot_commit','freeze_committed'),'FREEZE',name,errs)
        failures=as_int(first(d,'critical_control_failure_count','critical_control_failures'),0)
        if failures!=0:errs.append(f'CRITICAL_CONTROL_FAILURE:{name}:{failures}')
        ov=first(d,'oversize_control_key_counts','critical_control_oversize_counts','critical_control_oversize_count','critical_control_oversize')
        if not empty_oversize(ov):errs.append(f'CRITICAL_CONTROL_OVERSIZE:{name}:{ov!r}')
        fg=first(d,'foreground_valid','foreground_validity','foreground_interval_valid')
        if fg is None:errs.append(f'FOREGROUND_VALIDITY_REQUIRED:{name}')
        elif not as_bool(fg):errs.append(f'FOREGROUND_INVALID:{name}')
    empty=sum('SMOKE_CAL_EMPTY' in x.upper() or ('EMPTY' in x.upper() and 'HUMAN' not in x.upper()) for x in scenarios);human=sum('HUMAN_MOVING' in x.upper() or ('HUMAN' in x.upper() and 'MOV' in x.upper()) for x in scenarios)
    if rows and (empty!=3 or human!=3):errs.append(f'SCENARIOS_REQUIRED_3_EMPTY_3_HUMAN:empty={empty}:human={human}')
    unique_nodes={x for x in node_ids if x}
    if len(unique_nodes)!=3:errs.append(f'EXACTLY_3_UNIQUE_NODES_REQUIRED:{len(unique_nodes)}:{sorted(unique_nodes)}')
    def same(values,label,ignore=('',None,-1,())):
        clean=[v for v in values if v not in ignore]
        if not clean:errs.append(f'{label}_REQUIRED_ALL_FILES');return
        if len(set(clean))!=1:errs.append(f'{label}_MISMATCH:{sorted(map(str,set(clean)))}')
    for v,l in [(cal_ids,'CALIBRATION_ID'),(cal_hashes,'CALIBRATION_HASH'),(cal_gens,'CALIBRATION_GENERATION'),(topo_hashes,'TOPOLOGY_HASH'),(coord_ids,'COORDINATOR_ID'),(coord_gens,'COORDINATOR_GENERATION'),(authority_digests,'AUTHORITY_DIGEST'),(tokens,'CAMPAIGN_RUN_TOKEN')]:same(v,l)
    groups={}
    for i,sc in enumerate(scenarios):groups.setdefault(sc.upper(),[]).append(i)
    for sc,idx in groups.items():
        if len(idx)!=3:continue
        ss={sessions[i] for i in idx if sessions[i]};cc={cohorts[i] for i in idx if cohorts[i]}
        if len(ss)!=1:errs.append(f'SESSION_MISMATCH_IN_SCENARIO:{sc}:{sorted(ss)}')
        if len(cc)!=1:errs.append(f'COHORT_MISMATCH_IN_SCENARIO:{sc}:{sorted(map(str,cc))}')
    out={'schema':'G10Dev2017PhysicalValidationV1','release':'dev-20.17','files':len(paths),'unique_nodes':sorted(unique_nodes),'scenarios':{'SMOKE_CAL_EMPTY':empty,'HUMAN_MOVING':human},'minimum_duration_ms':MIN_DURATION_MS,'errors':errs,'g10':'GO' if not errs else 'NO_GO','g10_go':not errs,'g11':'UNBLOCKED' if not errs else 'BLOCKED','dev21':'UNBLOCKED' if not errs else 'BLOCKED','screenshots_required':False}
    text=json.dumps(out,indent=2,sort_keys=True);print(text)
    if ns.output:Path(ns.output).write_text(text+'\n',encoding='utf-8')
    return 0 if not errs else 2
if __name__=='__main__':sys.exit(main())
