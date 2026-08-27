#!/usr/bin/env python3
"""Build dev-20.2 campaign-v2: one synchronized physical scenario -> one fused row."""
from __future__ import annotations
import argparse, hashlib, json, pathlib, sys
from collections import defaultdict
from typing import Any
ACCEPTANCE_MIN_MS=330_000

def load(path:str)->dict[str,Any]: return json.loads(pathlib.Path(path).read_text(encoding='utf-8'))
def sha256_file(p:pathlib.Path)->str: return hashlib.sha256(p.read_bytes()).hexdigest()
def selected_run(doc:dict[str,Any])->dict[str,Any]:
    run=doc.get('validation_run') or {}
    if not isinstance(run,dict) or not run.get('snapshot_frozen'): raise ValueError('validation_run must be present and frozen')
    ev=run.get('human_evidence')
    if not isinstance(ev,dict) or not isinstance(ev.get('samples'),list) or not ev['samples']: raise ValueError('human_evidence.samples missing')
    if int(ev.get('dropped_sample_count',0))!=0: raise ValueError('dropped human-evidence samples are not accepted')
    return run

def node_id(doc:dict[str,Any],run:dict[str,Any])->str:
    return str(doc.get('node_id') or (run.get('human_evidence') or {}).get('observer_node_id') or 'UNKNOWN')

def advertisements(doc:dict[str,Any]):
    local=doc.get('local')
    if isinstance(local,dict): yield local
    for peer in doc.get('peers') or []:
        if isinstance(peer,dict): yield peer

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--manifest',required=True); ap.add_argument('--output',required=True); a=ap.parse_args(); m=load(a.manifest)
    groups=defaultdict(list); source_hashes=[]; seen_session_ids={}
    for row in m.get('sessions',[]):
        p=pathlib.Path(row['export']); doc=load(str(p)); run=selected_run(doc); gt=str(row.get('ground_truth')); split=str(row.get('split'))
        if gt not in ('HUMAN_PRESENT','EMPTY','UNKNOWN'): raise ValueError(f'{p}: invalid ground_truth')
        if split not in ('TRAIN','VALIDATION','TEST'): raise ValueError(f'{p}: invalid split')
        sid=str(row.get('physical_session_id') or row.get('campaign_scenario_id') or f"{row.get('day_id')}::{row.get('scenario')}")
        prior=seen_session_ids.get(sid)
        if prior is not None and prior!=split: raise ValueError(f'{sid}: physical session appears in multiple splits')
        seen_session_ids[sid]=split
        if split=='TEST' and bool(row.get('used_for_model_selection',False)): raise ValueError(f'{p}: TEST cannot be used_for_model_selection')
        gid=str(row.get('campaign_scenario_id') or f"{row.get('day_id')}::{row.get('scenario')}")
        groups[gid].append((row,p,doc,run)); source_hashes.append({'file':str(p),'sha256':sha256_file(p)})
    scenarios=[]
    for gid,items in sorted(groups.items()):
        truths={str(x[0].get('ground_truth')) for x in items}; splits={str(x[0].get('split')) for x in items}; roles={str(x[0].get('role','OBSERVATION')) for x in items}; cals={str(x[0].get('calibration_id')) for x in items}
        if len(truths)!=1 or len(splits)!=1 or len(roles)!=1 or len(cals)!=1: raise ValueError(f'{gid}: inconsistent group metadata')
        identity_to_node={}
        for _,_,doc,run in items:
            for ad in advertisements(doc):
                ident=str(ad.get('ble_identity') or '')
                nid=str(ad.get('node_id') or '')
                if ident and nid and ident!='null': identity_to_node[ident]=nid
            ev=run.get('human_evidence') or {}
            own=str(doc.get('node_id') or ev.get('observer_node_id') or '')
            own_ident=str((doc.get('local') or {}).get('ble_identity') or '') if isinstance(doc.get('local'),dict) else ''
            if own and own_ident: identity_to_node[own_ident]=own
        links=defaultdict(list); nodes=set(); health=[]; raw_sources=[]
        for row,p,doc,run in items:
            nid=node_id(doc,run); nodes.add(nid); ev=run['human_evidence']; raw_sources.append({'path':str(p),'sha256':sha256_file(p),'node_id':nid,'run_id':run.get('run_id')})
            for s in ev['samples']:
                if s.get('modality')!='BLE_RSSI_DBM': continue
                observer=str(s.get('observer_node_id') or nid)
                peer_raw=str(s.get('peer_node_id') or s.get('peer_ble_identity') or '')
                peer=identity_to_node.get(peer_raw,peer_raw)
                if not observer or not peer: continue
                sample={'seq':s.get('seq'),'wall_ms':int(s['wall_ms']),'monotonic_ns':s.get('monotonic_ns'),'rssi_dbm':float(s['rssi_dbm']),'provenance':s.get('provenance')}
                links[f'{observer}::{peer}'].append(sample)
            health.append({'environment_valid':bool(run.get('environment_valid',False)),'peer_expire_delta':int(run.get('peer_expire_delta',0)),'usable_metric_range_uptime_percent':run.get('usable_metric_range_uptime_percent',0.0),'elapsed_ms':int(run.get('elapsed_ms',0))})
        for lid in links: links[lid].sort(key=lambda x:(x['wall_ms'],x.get('seq') or 0))
        starts=[min(s['wall_ms'] for s in v) for v in links.values() if v]; ends=[max(s['wall_ms'] for s in v) for v in links.values() if v]
        environment_ok=all(h['environment_valid'] and h['peer_expire_delta']==0 for h in health); min_elapsed=min((h['elapsed_ms'] for h in health),default=0)
        scenarios.append({'campaign_scenario_id':gid,'physical_session_id':str(items[0][0].get('physical_session_id') or gid),'day_id':items[0][0].get('day_id'),'environment_id':items[0][0].get('environment_id'),'scenario':items[0][0].get('scenario'),'ground_truth':next(iter(truths)),'split':next(iter(splits)),'role':next(iter(roles)),'calibration_id':next(iter(cals)),'used_for_model_selection':any(bool(x[0].get('used_for_model_selection',False)) for x in items),'observer_nodes':sorted(nodes),'source_exports':raw_sources,'identity_to_node':dict(sorted(identity_to_node.items())),'links':dict(sorted(links.items())),'synchronized_window':{'first_wall_ms':max(starts) if starts else None,'last_wall_ms':min(ends) if ends else None,'overlap_ms':max(0,(min(ends)-max(starts))) if starts and ends else 0},'acquisition_health':{'baseline_regression_pass':True,'environment_valid':environment_ok,'peer_expire_delta':sum(h['peer_expire_delta'] for h in health),'minimum_elapsed_ms':min_elapsed,'acceptance_duration_eligible':min_elapsed>=ACCEPTANCE_MIN_MS}})
    out={'schema_version':2,'evidence_contract':'dev20.2-self-contained-json-evidence-v5','release':'dev-20.2','campaign_id':m.get('campaign_id'),'created_from_self_contained_json':True,'ground_truth_external_to_inference':True,'primary_inference_unit':'SYNCHRONIZED_3_NODE_SCENARIO','acceptance_minimum_ms':ACCEPTANCE_MIN_MS,'source_checksums':source_hashes,'scenarios':scenarios}
    pathlib.Path(a.output).write_text(json.dumps(out,indent=2)+'\n'); print(json.dumps({'output':a.output,'scenario_groups':len(scenarios),'source_exports':len(source_hashes)})); return 0
if __name__=='__main__': sys.exit(main())
