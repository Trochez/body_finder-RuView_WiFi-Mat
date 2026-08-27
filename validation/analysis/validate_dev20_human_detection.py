#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,pathlib,sys
from dev20_2_fusion import infer_fused_presence, canonical_result, ALGORITHM_VERSION, PARAMETER_HASH

def confusion(rows):
    tp=tn=fp=fn=ind=0
    for r in rows:
        gt=r.get('ground_truth'); pr=r.get('prediction')
        if pr=='INDETERMINATE': ind+=1; continue
        if gt=='HUMAN_PRESENT':
            if pr=='HUMAN_EVIDENCE': tp+=1
            elif pr=='NO_HUMAN_EVIDENCE': fn+=1
        elif gt=='EMPTY':
            if pr=='NO_HUMAN_EVIDENCE': tn+=1
            elif pr=='HUMAN_EVIDENCE': fp+=1
    rec=tp/(tp+fn) if tp+fn else None; spec=tn/(tn+fp) if tn+fp else None; prec=tp/(tp+fp) if tp+fp else None
    f1=(2*prec*rec/(prec+rec)) if prec is not None and rec is not None and (prec+rec)>0 else None
    return {'tp':tp,'tn':tn,'fp':fp,'fn':fn,'indeterminate':ind,'total':len(rows),'recall':rec,'specificity':spec,'precision':prec,'f1':f1,'fpr':(fp/(fp+tn) if fp+tn else None),'indeterminate_rate':(ind/len(rows) if rows else None)}

def report_metrics(rows):
    fam={s:confusion([r for r in rows if r.get('scenario')==s]) for s in sorted({str(r.get('scenario')) for r in rows})}
    return {'overall':confusion(rows),'by_scenario':fam,'stationary_human':confusion([r for r in rows if r.get('scenario')=='HUMAN_STATIONARY_CENTER']),'moving_human':confusion([r for r in rows if r.get('scenario')=='HUMAN_MOVING']),'negative_controls':confusion([r for r in rows if r.get('ground_truth')=='EMPTY'])}

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('campaign'); ap.add_argument('--output',required=True); ap.add_argument('--final-test',action='store_true'); ap.add_argument('--engineering-regression',action='store_true'); a=ap.parse_args()
    doc=json.loads(pathlib.Path(a.campaign).read_text()); scenarios=doc.get('scenarios',[]); failures=[]
    if doc.get('schema_version')!=2: failures.append('campaign schema_version must be 2')
    if not doc.get('ground_truth_external_to_inference'): failures.append('ground truth must be external to inference')
    cal={}
    for s in scenarios:
        if s.get('role')=='CALIBRATION' and s.get('ground_truth')=='EMPTY': cal[str(s.get('calibration_id'))]=s.get('links') or {}
    rows=[]
    for s in scenarios:
        if s.get('role')=='CALIBRATION': continue
        cid=str(s.get('calibration_id')); baseline=cal.get(cid); result=None
        if not baseline: failures.append(f"{s.get('campaign_scenario_id')}: missing EMPTY calibration {cid}")
        else:
            result=infer_fused_presence(baseline,s.get('links') or {},acquisition_health=s.get('acquisition_health') or {})
            replay=infer_fused_presence(baseline,s.get('links') or {},acquisition_health=s.get('acquisition_health') or {})
            if canonical_result(result)!=canonical_result(replay): failures.append(f"{s.get('campaign_scenario_id')}: nondeterministic replay")
        pred=result.prediction if result else 'INDETERMINATE'; hp=.5
        if result:
            hp=result.human_confidence if pred=='HUMAN_EVIDENCE' else 1-result.human_confidence if pred=='NO_HUMAN_EVIDENCE' else .5
        rows.append({'campaign_scenario_id':s.get('campaign_scenario_id'),'physical_session_id':s.get('physical_session_id'),'device_id':'FUSED_3_NODE','environment_id':s.get('environment_id'),'day_id':s.get('day_id'),'scenario':s.get('scenario'),'ground_truth':s.get('ground_truth'),'split':s.get('split'),'used_for_model_selection':bool(s.get('used_for_model_selection',False)),'prediction':pred,'human_probability':hp,'fusion':json.loads(canonical_result(result)) if result else {}})
    eval_rows=[r for r in rows if r.get('split')=='TEST'] if a.final_test else rows
    if a.final_test:
        if not eval_rows: failures.append('no TEST scenarios')
        leaked=[str(r['campaign_scenario_id']) for r in eval_rows if r.get('used_for_model_selection')]
        if leaked: failures.append('TEST used for model selection: '+','.join(leaked))
        split_map={}
        for r in rows:
            ps=str(r.get('physical_session_id')); sp=str(r.get('split')); old=split_map.setdefault(ps,sp)
            if old!=sp: failures.append(f'physical session leakage: {ps} in {old}/{sp}')
    bad=[str(s.get('campaign_scenario_id')) for s in scenarios if s.get('role')!='CALIBRATION' and (not (s.get('acquisition_health') or {}).get('environment_valid',False) or int((s.get('acquisition_health') or {}).get('peer_expire_delta',0))!=0)]
    if bad: failures.append('acquisition/environment gate failed: '+','.join(bad))
    m=report_metrics(eval_rows); ov=m['overall']
    if a.final_test:
        if (ov.get('recall') or 0)<.90: failures.append(f"recall target not met: {ov.get('recall')} < 0.90")
        if (ov.get('specificity') or 0)<.85: failures.append(f"specificity target not met: {ov.get('specificity')} < 0.85")
        if (ov.get('indeterminate_rate') or 0)>.10: failures.append(f"indeterminate rate too high: {ov.get('indeterminate_rate')} > 0.10")
        sr=m['stationary_human'].get('recall'); mr=m['moving_human'].get('recall')
        if sr is None or sr<.80: failures.append(f'stationary-human recall target not met: {sr}')
        if mr is None or mr<.90: failures.append(f'moving-human recall target not met: {mr}')
    physical='PASS' if a.final_test and not failures else ('FAIL' if a.final_test else 'PENDING')
    out={'schema_version':2,'release':'dev-20.2','algorithm_version':ALGORITHM_VERSION,'detector_parameter_hash':PARAMETER_HASH,'primary_inference_unit':'SYNCHRONIZED_3_NODE_SCENARIO','baseline_regression':'PASS' if not bad else 'FAIL','physical_acceptance':physical,'final_go':bool(a.final_test and not failures),'metrics':m,'scenarios':rows,'failures':failures,'screenshots_required':False,'human_localization_validated':False,'rescue_use_validated':False,'claims_blocked':['localization','rescue_use','proof_of_absence']}
    pathlib.Path(a.output).write_text(json.dumps(out,indent=2)+'\n'); print(json.dumps({'final_go':out['final_go'],'physical_acceptance':physical,'metrics':ov,'failures':failures},indent=2))
    if a.final_test: return 0 if out['final_go'] else 2
    return 2 if a.engineering_regression and failures else 0
if __name__=='__main__': sys.exit(main())
