#!/usr/bin/env python3
from __future__ import annotations
import json, sys
from collections import Counter,defaultdict
from pathlib import Path

BUILD='0.2.0-experimental.16'; SCHEMA=4; PROTOCOL=2
UNFILTERED_TARGET=9500; UNFILTERED_HARD=10000
PROBE_TARGET=14500; PROBE_HARD=15000
ROLLING_WINDOW=300000; ROLLING_LIMIT=3
class ContractError(Exception): pass
def req(o,k,p='$'):
    if not isinstance(o,dict) or k not in o: raise ContractError(f'MISSING_REQUIRED_FIELD:{p}.{k}')
    return o[k]
def req_int(o,k,p='$'):
    v=req(o,k,p)
    if type(v) is not int: raise ContractError(f'INVALID_TYPE_INT:{p}.{k}')
    return v
def req_num(o,k,p='$'):
    v=req(o,k,p)
    if type(v) not in (int,float): raise ContractError(f'INVALID_TYPE_NUMBER:{p}.{k}')
    return float(v)
def req_str(o,k,p='$'):
    v=req(o,k,p)
    if not isinstance(v,str) or not v: raise ContractError(f'INVALID_TYPE_STRING:{p}.{k}')
    return v
def req_bool(o,k,p='$'):
    v=req(o,k,p)
    if type(v) is not bool: raise ContractError(f'INVALID_TYPE_BOOL:{p}.{k}')
    return v
def req_dict(o,k,p='$'):
    v=req(o,k,p)
    if not isinstance(v,dict): raise ContractError(f'INVALID_TYPE_DICT:{p}.{k}')
    return v
def req_list(o,k,p='$'):
    v=req(o,k,p)
    if not isinstance(v,list): raise ContractError(f'INVALID_TYPE_LIST:{p}.{k}')
    return v

def recovery_analysis(run):
    errors=[]; warnings=[]; infos=[]; groups=defaultdict(list); requests=[]
    events=req_list(run,'events','$.validation_run')
    for i,e in enumerate(events):
        if not isinstance(e,dict): errors.append(f'INVALID_EVENT_TYPE:{i}'); continue
        try: typ=req_str(e,'type',f'$.validation_run.events[{i}]'); req_int(e,'seq',f'$.validation_run.events[{i}]'); req_num(e,'wall_ms',f'$.validation_run.events[{i}]')
        except ContractError as x: errors.append(str(x)); continue
        g=e.get('recovery_generation')
        if type(g) is int: groups[g].append(e)
        if typ=='RECOVERY_REQUESTED':
            if type(g) is not int: errors.append(f'MISSING_RECOVERY_GENERATION:{i}')
            else: requests.append(float(e['wall_ms']))
    totals=Counter(); peers=defaultdict(Counter); maxu=maxp=0
    for g,es in sorted(groups.items()):
        es=sorted(es,key=lambda e:e['seq']); r=[e for e in es if e['type']=='RECOVERY_REQUESTED']; f=[e for e in es if e['type']=='FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY']; ok=[e for e in es if e['type']=='RECOVERY_SUCCESS']; bad=[e for e in es if e['type']=='RECOVERY_FAILURE']; term=ok+bad
        if not (r or f or term): continue
        if len(r)!=1: errors.append(f'RECOVERY_REQUEST_COUNT_INVALID:g{g}'); continue
        if len(term)!=1: errors.append(f'RECOVERY_TERMINAL_COUNT_INVALID:g{g}'); continue
        d=float(term[0]['wall_ms'])-float(r[0]['wall_ms']); maxu=max(maxu,int(d))
        if d<0: errors.append(f'UNFILTERED_DURATION_INVALID:g{g}')
        elif d>UNFILTERED_HARD: errors.append(f'UNFILTERED_HARD_LIMIT_BREACHED:g{g}:{int(d)}')
        elif d>UNFILTERED_TARGET: warnings.append(f'UNFILTERED_ACTION_TARGET_MISSED:g{g}:{int(d)}')
        if ok:
            if len(f)!=1: errors.append(f'RECOVERY_FIRST_VALID_COUNT_INVALID:g{g}')
            elif not (r[0]['seq']<f[0]['seq']<ok[0]['seq']): errors.append(f'RECOVERY_CAUSAL_ORDER_INVALID:g{g}')
        elif f: errors.append(f'FIRST_VALID_WITH_FAILURE:g{g}')
        trig=r[0].get('trigger_kind'); target=r[0].get('trigger_peer_id') or r[0].get('peer_id')
        if trig=='PEER_STARVATION':
            totals['targeted_request']+=1
            if not isinstance(target,str) or not target: errors.append(f'RECOVERY_TARGET_MISSING:g{g}')
            else:
                peers[target]['request']+=1
                if f:
                    totals['first']+=1; peers[target]['first']+=1
                    if f[0].get('peer_id')!=target: errors.append(f'FIRST_VALID_WRONG_TARGET:g{g}')
                if ok:
                    totals['targeted_success']+=1; peers[target]['success']+=1
                    if ok[0].get('peer_id')!=target: errors.append(f'RECOVERY_SUCCESS_WRONG_TARGET:g{g}')
                if bad: totals['targeted_failure']+=1; peers[target]['failure']+=1
        elif f: totals['first']+=1
        ps=[e for e in es if e['type']=='ACQUISITION_STRATEGY_CHANGED' and e.get('to_strategy')=='FILTERED_RECOVERY_PROBE']
        pe=[e for e in es if e['type']=='ACQUISITION_STRATEGY_CHANGED' and e.get('from_strategy')=='FILTERED_RECOVERY_PROBE']
        if len(ps)!=1: errors.append(f'RECOVERY_PROBE_START_INVALID:g{g}')
        else:
            end=float(pe[0]['wall_ms']) if len(pe)==1 else req_num(run,'ended_wall_ms','$.validation_run')
            d=end-float(ps[0]['wall_ms']); maxp=max(maxp,int(d))
            if d<0: errors.append(f'FILTERED_PROBE_DURATION_INVALID:g{g}')
            elif d>PROBE_HARD: errors.append(f'FILTERED_PROBE_HARD_LIMIT_BREACHED:g{g}:{int(d)}')
            elif d>PROBE_TARGET: warnings.append(f'FILTERED_PROBE_EXIT_TARGET_MISSED:g{g}:{int(d)}')
    requests.sort(); roll=max((sum(1 for x in requests if t<=x<=t+ROLLING_WINDOW) for t in requests),default=0)
    if roll>ROLLING_LIMIT: errors.append(f'RECOVERY_BUDGET_EXCEEDED:{roll}')
    return {'errors':list(dict.fromkeys(errors)),'warnings':list(dict.fromkeys(warnings)),'informational':infos,'max_rolling':roll,'total_requests':len(requests),'max_unfiltered':maxu,'max_probe':maxp,'totals':totals,'peers':peers}

def validate_export(doc,acceptance=True,ignore_three_node=False):
    gates={f'G{i}':{'pass':True,'errors':[]} for i in range(17)}; warnings=[]; info=[]
    def fail(g,c): gates[g]['pass']=False; gates[g]['errors'].append(c) if c not in gates[g]['errors'] else None
    try: run=req_dict(doc,'validation_run')
    except ContractError as e: fail('G0',str(e)); return {'pass':False,'gates':gates,'warnings':warnings,'informational':info}
    try:
        if req_str(doc,'build')!=BUILD: fail('G0','BUILD_MISMATCH')
        if req_int(doc,'protocol_version')!=PROTOCOL: fail('G0','PROTOCOL_MISMATCH')
        if req_int(run,'snapshot_schema_version','$.validation_run')!=SCHEMA: fail('G0','SNAPSHOT_SCHEMA_DRIFT')
        if req_bool(run,'snapshot_frozen','$.validation_run') is not True: fail('G0','SNAPSHOT_NOT_FROZEN')
        if req_bool(doc,'json_self_contained') is not True or req_bool(doc,'screenshots_required') is not False: fail('G0','EVIDENCE_CONTRACT_DRIFT')
    except ContractError as e: fail('G0',str(e))
    try:
        pf=req_dict(run,'preflight_at_start','$.validation_run')
        if req_bool(pf,'ready','$.validation_run.preflight_at_start') is not True: fail('G2','PREFLIGHT_NOT_READY')
    except ContractError as e: fail('G2',str(e))
    try:
        if acceptance and req_num(run,'elapsed_ms','$.validation_run')<300000: fail('G3','LONG_RUN_INELIGIBLE')
    except ContractError as e: fail('G3',str(e))
    try:
        env=req_dict(run,'environment','$.validation_run')
        if req_bool(env,'valid','$.validation_run.environment') is not True: fail('G4','ENVIRONMENT_INVALID')
    except ContractError as e: fail('G4',str(e))
    try:
        acq=req_dict(run,'acquisition_state_at_end','$.validation_run')
        required={'recovery_unfiltered_hard_limit_ms':10000,'recovery_unfiltered_action_target_ms':9500,'filtered_probe_exit_target_ms':14500,'filtered_probe_hard_limit_ms':15000,'filtered_probe_action_target_ms':14000,'recovery_budget_window_ms':300000,'recovery_budget_limit':3}
        for k,v in required.items():
            if req_int(acq,k,'$.validation_run.acquisition_state_at_end')!=v: fail('G14',f'FROZEN_VALUE_DRIFT:{k}')
        req_int(acq,'recovery_attempt_delta_total','$.validation_run.acquisition_state_at_end'); req_int(acq,'recovery_attempts_in_current_5min_window_at_end','$.validation_run.acquisition_state_at_end'); frozen_roll=req_int(acq,'recovery_attempts_max_in_any_rolling_5min_window','$.validation_run.acquisition_state_at_end')
        if acceptance:
            if req_str(acq,'logical_acquisition_strategy','$.validation_run.acquisition_state_at_end')!='FILTERED_PRIMARY': fail('G5','LONG_END_NOT_FILTERED_PRIMARY')
            if req(acq,'active_recovery_generation','$.validation_run.acquisition_state_at_end') is not None: fail('G5','ACTIVE_RECOVERY_AT_LONG_END')
            if req(acq,'strategy_recovery_generation','$.validation_run.acquisition_state_at_end') is not None: fail('G5','STRATEGY_RECOVERY_AT_LONG_END')
    except ContractError as e: fail('G5',str(e)); fail('G14',str(e)); frozen_roll=None
    try:
        if acceptance and not ignore_three_node and req_num(run,'all_expected_peer_metric_uptime_percent','$.validation_run')<90: fail('G6','ALL_EXPECTED_PEER_METRIC_UPTIME_LOW')
        if acceptance and not ignore_three_node and req_num(run,'geometry_2d_uptime_percent','$.validation_run')<90: fail('G7','GEOMETRY2D_UPTIME_LOW')
    except ContractError as e: fail('G6',str(e)); fail('G7',str(e))
    try:
        c=req_dict(run,'validation_counters','$.validation_run')
        if req_int(c,'peer_expire_delta','$.validation_run.validation_counters')!=0: fail('G8','PEER_EXPIRE_NONZERO')
    except ContractError as e: fail('G8',str(e))
    try:
        ra=recovery_analysis(run); warnings+=ra['warnings']; info+=ra['informational']
        for e in ra['errors']:
            if 'BUDGET' in e: fail('G9',e)
            elif 'WRONG_TARGET' in e or 'TARGET_MISSING' in e: fail('G11',e)
            elif 'HARD_LIMIT' in e: fail('G13',e)
            else: fail('G10',e)
        if frozen_roll is not None and frozen_roll!=ra['max_rolling']: fail('G12',f'ROLLING_SUMMARY_EVENT_MISMATCH:{frozen_roll}!={ra["max_rolling"]}')
        ts=req_dict(run,'recovery_timing_summary','$.validation_run')
        checks={'max_unfiltered_duration_ms':ra['max_unfiltered'],'max_filtered_probe_duration_ms':ra['max_probe']}
        for k,v in checks.items():
            if req_int(ts,k,'$.validation_run.recovery_timing_summary')!=v: fail('G12',f'TIMING_SUMMARY_EVENT_MISMATCH:{k}')
        if req_int(ts,'unfiltered_hard_limit_breach_count','$.validation_run.recovery_timing_summary')!=0: fail('G13','UNFILTERED_HARD_BREACH_SUMMARY')
        if req_int(ts,'filtered_probe_hard_limit_breach_count','$.validation_run.recovery_timing_summary')!=0: fail('G13','FILTERED_PROBE_HARD_BREACH_SUMMARY')
    except ContractError as e: fail('G12',str(e)); fail('G13',str(e)); ra={'totals':Counter()}
    # G15 history and G16 campaign are aggregate validators, not single-export gates.
    ok=all(v['pass'] for v in gates.values())
    return {'pass':ok,'gates':gates,'warnings':list(dict.fromkeys(warnings)),'informational':list(dict.fromkeys(info)),'recovery':{k:v for k,v in ra.items() if k not in ('totals','peers')}}

def load_exports(d):
    out=[]
    for p in sorted(Path(d).glob('*.json')):
        try:
            x=json.load(open(p)); out.append((p,x))
        except Exception: pass
    return out

def validate_campaign(d,directed=False):
    rows=[]; targeted=0; bydev=defaultdict(dict)
    for p,x in load_exports(d):
        r=validate_export(x,acceptance=not (x.get('export_metadata',{}).get('snapshot_stage')=='SHORT'),ignore_three_node=directed)
        rows.append({'file':p.name,**r})
        md=x.get('export_metadata',{}); dev=md.get('device_alias') or md.get('device_model') or p.name; stage=md.get('snapshot_stage'); run=x.get('validation_run',{})
        if stage: bydev[dev][stage]=(x,run)
        for e in run.get('events',[]):
            if e.get('type')=='RECOVERY_SUCCESS' and e.get('trigger_kind')=='PEER_STARVATION': targeted+=1
    errors=[]
    if directed:
        if len(bydev)<2: errors.append('DIRECTED_REQUIRES_TWO_DEVICES')
        for dev,st in bydev.items():
            miss={'LONG_1','LONG_2','SHORT','LONG_POST_SHORT'}-set(st)
            if miss: errors.append(f'MISSING_STAGES:{dev}:{sorted(miss)}'); continue
            a=st['LONG_1'][1]; b=st['LONG_2'][1]; c=st['LONG_POST_SHORT'][1]; short=st['SHORT'][1]
            if not (a.get('run_id')==b.get('run_id')==c.get('run_id')): errors.append(f'HISTORY_RUN_ID_CHANGED:{dev}')
            def stable(j):
                z=dict(j); z.pop('snapshot_identity_sha256',None); return z
            if not (stable(a)==stable(b)==stable(c)): errors.append(f'HISTORY_SNAPSHOT_MUTATED:{dev}')
            if short.get('run_id')==a.get('run_id'): errors.append(f'SHORT_RUN_ID_REUSED:{dev}')
            if st['SHORT'][0].get('export_metadata',{}).get('source_long_run_id')!=a.get('run_id'): errors.append(f'SHORT_SOURCE_LONG_MISMATCH:{dev}')
        if targeted<1: errors.append('CAMPAIGN_TARGETED_PEER_STARVATION_REQUIRED')
    return {'pass':all(r['pass'] for r in rows) and not errors,'directed':directed,'targeted_recovery_success_count':targeted,'campaign_errors':errors,'results':rows}
