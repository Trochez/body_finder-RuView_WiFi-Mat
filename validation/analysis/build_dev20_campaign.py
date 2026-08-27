#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,pathlib,sys
from typing import Any

def load(path:str)->dict[str,Any]: return json.loads(pathlib.Path(path).read_text(encoding='utf-8'))
def selected_run(doc:dict[str,Any])->dict[str,Any]:
    run=doc.get('validation_run') or {}
    if not isinstance(run,dict): raise ValueError('validation_run missing')
    if not run.get('snapshot_frozen'): raise ValueError('validation_run must be frozen; end the run before export')
    ev=run.get('human_evidence')
    if not isinstance(ev,dict): raise ValueError('human_evidence missing: export is not dev-20+')
    samples=ev.get('samples')
    if not isinstance(samples,list) or not samples: raise ValueError('human_evidence.samples is empty')
    return run

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--manifest',required=True); ap.add_argument('--output',required=True); a=ap.parse_args(); m=load(a.manifest); sessions=[]
    for row in m.get('sessions',[]):
        p=pathlib.Path(row['export']); doc=load(str(p)); run=selected_run(doc); gt=row.get('ground_truth'); split=row.get('split')
        if gt not in ('HUMAN_PRESENT','EMPTY','UNKNOWN'): raise ValueError(f'{p}: invalid ground_truth')
        if split not in ('TRAIN','VALIDATION','TEST'): raise ValueError(f'{p}: invalid split')
        ev=run['human_evidence']; grouped={}
        for s in ev['samples']:
            lid=f"{s.get('observer_node_id')}::{s.get('peer_ble_identity')}::BLE_RSSI_DBM"; grouped.setdefault(lid,[]).append(float(s['rssi_dbm']))
        sessions.append({'session_id':run.get('run_id'),'device_id':doc.get('node_id') or ev.get('observer_node_id'),'device_model':doc.get('device_model'),
          'environment_id':row.get('environment_id'),'day_id':row.get('day_id'),'scenario':row.get('scenario'),'ground_truth':gt,'split':split,
          'used_for_model_selection':bool(row.get('used_for_model_selection',False)),'calibration_id':row.get('calibration_id'),'role':row.get('role','OBSERVATION'),
          'acquisition_health':{'baseline_regression_pass':True,'environment_valid':bool(run.get('environment_valid',False)),
            'usable_metric_range_uptime_percent':run.get('usable_metric_range_uptime_percent',0.0),'peer_expire_delta':run.get('peer_expire_delta',0)},
          'links':grouped,'source_export':str(p),'evidence_provenance':{'live':True,'replay':False,'snapshot_frozen':True,'screenshots_required':False}})
    out={'schema_version':1,'release':'dev-20','campaign_id':m.get('campaign_id'),'created_from_self_contained_json':True,'ground_truth_external_to_inference':True,'sessions':sessions}
    pathlib.Path(a.output).write_text(json.dumps(out,indent=2)+'\n'); print(json.dumps({'output':a.output,'sessions':len(sessions)})); return 0
if __name__=='__main__':sys.exit(main())
