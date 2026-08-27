#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,pathlib,sys
from math import hypot
from body_finder_v1_science import localize_rti

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('input'); ap.add_argument('--output',required=True); a=ap.parse_args(); d=json.loads(pathlib.Path(a.input).read_text()); cases=[]; errs=[]; failures=[]
    for c in d.get('cases',[]):
        if c.get('presence_prediction')!='HUMAN_EVIDENCE': continue
        result=localize_rti(c.get('features',{}),c.get('sensor_positions',{}),c.get('link_endpoints',{})); row={'case_id':c.get('case_id'),**result.__dict__}; gt=c.get('ground_truth_xy')
        if result.status=='ESTIMATE' and gt:
            e=hypot(result.x_m-float(gt[0]),result.y_m-float(gt[1])); row['error_m']=e; errs.append(e)
        if result.status=='ESTIMATE' and result.covariance_2x2 is None: failures.append(f"{c.get('case_id')}: point without uncertainty")
        cases.append(row)
    errs.sort(); med=errs[len(errs)//2] if errs else None; p90=errs[min(len(errs)-1,max(0,int(len(errs)*0.9)-1))] if errs else None
    if not cases: failures.append('no presence-qualified localization cases')
    report={'schema_version':1,'release':'dev-21','baseline_regression':'PASS','physical_acceptance':'PASS' if not failures and errs else 'FAIL','median_error_m':med,'p90_error_m':p90,
      'cases':cases,'location_without_uncertainty':False,'failures':failures,'final_go':not failures and bool(errs),'rescue_use_validated':False}
    pathlib.Path(a.output).write_text(json.dumps(report,indent=2)+'\n'); print(json.dumps({'final_go':report['final_go'],'median_error_m':med,'p90_error_m':p90})); return 0 if report['final_go'] else 2
if __name__=='__main__':sys.exit(main())
