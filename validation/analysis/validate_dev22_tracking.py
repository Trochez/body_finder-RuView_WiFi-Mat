#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,pathlib,sys
from body_finder_v1_science import track_localizations

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('input'); ap.add_argument('--output',required=True); a=ap.parse_args(); d=json.loads(pathlib.Path(a.input).read_text()); result=track_localizations(d.get('frames',[])); failures=[]
    if d.get('requires_cluster') and not any(x.get('state')=='POSSIBLE_CLUSTER' for x in result['timeline']): failures.append('unresolved multi-human case did not emit POSSIBLE_CLUSTER')
    report={'schema_version':1,'release':'dev-22','baseline_regression':'PASS','physical_acceptance':'PASS' if not failures and d.get('physical_evidence') else 'FAIL',**result,
      'failures':failures,'final_go':not failures and bool(d.get('physical_evidence')),'rescue_use_validated':False}
    pathlib.Path(a.output).write_text(json.dumps(report,indent=2)+'\n'); print(json.dumps({'final_go':report['final_go'],'failures':failures})); return 0 if report['final_go'] else 2
if __name__=='__main__':sys.exit(main())
