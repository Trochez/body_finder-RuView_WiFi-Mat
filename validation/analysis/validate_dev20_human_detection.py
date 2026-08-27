#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,pathlib,sys
from collections import defaultdict
from body_finder_v1_science import infer_presence,evaluate_presence_rows

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('campaign'); ap.add_argument('--output',required=True); ap.add_argument('--engineering-targets',action='store_true'); a=ap.parse_args()
    doc=json.loads(pathlib.Path(a.campaign).read_text()); sessions=doc.get('sessions',[])
    if not doc.get('ground_truth_external_to_inference'): raise SystemExit('FAIL: ground truth must be external to inference')
    cal=defaultdict(lambda:defaultdict(list))
    for s in sessions:
        if s.get('role')=='CALIBRATION' and s.get('ground_truth')=='EMPTY':
            for lid,vals in (s.get('links') or {}).items(): cal[str(s.get('calibration_id'))][lid].extend(vals)
    rows=[]; failures=[]
    for s in sessions:
        if s.get('role')=='CALIBRATION': continue
        r=infer_presence(cal.get(str(s.get('calibration_id')),{ }),s.get('links') or {},acquisition_health=s.get('acquisition_health') or {})
        hp=r.human_confidence if r.prediction=='HUMAN_EVIDENCE' else (1-r.human_confidence if r.prediction=='NO_HUMAN_EVIDENCE' else 0.5)
        rows.append({**{k:s.get(k) for k in ('session_id','device_id','environment_id','day_id','scenario','ground_truth','split','used_for_model_selection')},
          'prediction':r.prediction,'human_probability':hp,'human_confidence':r.human_confidence,'evidence_quality':r.evidence_quality,
          'aggregate_change_score':r.aggregate_change_score,'feature_provenance':r.feature_provenance,'reason':r.reason})
    metrics=evaluate_presence_rows(rows); ov=metrics['overall']
    if a.engineering_targets:
        for key,thr in [('recall',0.90),('specificity',0.85)]:
            v=ov.get(key)
            if v is None or v<thr: failures.append(f'{key} target not met: {v} < {thr}')
    bad=[s.get('session_id') for s in sessions if s.get('role')!='CALIBRATION' and ((s.get('acquisition_health') or {}).get('peer_expire_delta',0)!=0 or not (s.get('acquisition_health') or {}).get('environment_valid',False))]
    if bad: failures.append('acquisition regression/invalid environment in sessions: '+','.join(map(str,bad)))
    report={'schema_version':1,'release':'dev-20','baseline_regression':'PASS' if not bad else 'FAIL','physical_acceptance':'PASS' if not failures else 'FAIL',
      'claims_allowed':['HUMAN_EVIDENCE','NO_HUMAN_EVIDENCE','INDETERMINATE'] if not failures else [],'claims_blocked':['localization','rescue_use','proof_of_absence'],
      'metrics':metrics,'sessions':rows,'failures':failures,'final_go':not failures,'human_localization_validated':False,'rescue_use_validated':False}
    pathlib.Path(a.output).write_text(json.dumps(report,indent=2)+'\n'); print(json.dumps({'final_go':report['final_go'],'failures':failures,'metrics':ov},indent=2)); return 0 if report['final_go'] else 2
if __name__=='__main__':sys.exit(main())
