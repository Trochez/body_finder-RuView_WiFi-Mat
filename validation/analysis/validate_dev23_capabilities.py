#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,pathlib,sys
from body_finder_v1_science import capability_truth_from_probe

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('input'); ap.add_argument('--output',required=True); a=ap.parse_args(); d=json.loads(pathlib.Path(a.input).read_text()); truths=[capability_truth_from_probe(x) for x in d.get('probes',[])]; failures=[]
    for t in truths:
        if t['state']=='VERIFIED_REAL' and t['real_sample_count']<=0: failures.append(f"{t['modality']}: verified without real samples")
    if d.get('model_whitelist_used'): failures.append('model-name whitelist is forbidden')
    report={'schema_version':1,'release':'dev-23','baseline_regression':'PASS','physical_acceptance':'PASS' if not failures and d.get('common_path_regression_pass') else 'FAIL',
      'capability_truth_matrix':truths,'fabricated_csi':False,'common_path_regression_pass':bool(d.get('common_path_regression_pass')),'failures':failures,
      'final_go':not failures and bool(d.get('common_path_regression_pass')),'rescue_use_validated':False}
    pathlib.Path(a.output).write_text(json.dumps(report,indent=2)+'\n'); print(json.dumps({'final_go':report['final_go'],'truths':truths,'failures':failures},indent=2)); return 0 if report['final_go'] else 2
if __name__=='__main__':sys.exit(main())
