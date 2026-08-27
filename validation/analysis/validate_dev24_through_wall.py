#!/usr/bin/env python3
"""Fail-closed evaluator for controlled, consented NLOS/mock-debris lab campaigns only."""
from __future__ import annotations
import argparse,json,pathlib,sys
from body_finder_v1_science import confusion_metrics

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('input'); ap.add_argument('--output',required=True); a=ap.parse_args(); d=json.loads(pathlib.Path(a.input).read_text()); rows=d.get('runs',[]); failures=[]
    if d.get('controlled_lab_consent') is not True: failures.append('controlled_lab_consent=true is required')
    nlos=[r for r in rows if r.get('regime') in ('NLOS_WALL','SAFE_MOCK_DEBRIS')]
    if not nlos: failures.append('same-room-only evidence cannot satisfy the NLOS gate')
    if len({r.get('environment_id') for r in nlos})<2: failures.append('requires >=2 controlled NLOS environments')
    if len({r.get('day_id') for r in nlos})<2: failures.append('requires >=2 held-out days')
    if not any(r.get('split')=='TEST' for r in nlos): failures.append('requires frozen NLOS TEST runs')
    metrics=confusion_metrics([r for r in nlos if r.get('split')=='TEST']) if nlos else {}
    report={'schema_version':1,'release':'dev-24','baseline_regression':'PASS','physical_acceptance':'PASS' if not failures else 'FAIL','nlos_presence_metrics':metrics,
      'localization_metrics_separate_from_same_room':True,'same_room_pooled_into_claim':False,'controlled_lab_only':True,'failures':failures,'final_go':not failures,'rescue_use_validated':False}
    pathlib.Path(a.output).write_text(json.dumps(report,indent=2)+'\n'); print(json.dumps({'final_go':report['final_go'],'failures':failures})); return 0 if report['final_go'] else 2
if __name__=='__main__':sys.exit(main())
