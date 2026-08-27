#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,pathlib,sys

def sha256(p:pathlib.Path)->str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def gate(run:dict,name:str):
    return next((g for g in run.get('gates',[]) if g.get('gate')==name),None)

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--evidence-dir',default='evidence/dev-19/dev19-acceptance'); ap.add_argument('--output'); a=ap.parse_args()
    d=pathlib.Path(a.evidence_dir); failures=[]
    final=json.loads((d/'dev19-final-acceptance.json').read_text()); full=json.loads((d/'dev19-3android-acceptance.json').read_text())
    if not final.get('final_go') or final.get('three_android_acceptance')!='PASS': failures.append('dev19 final acceptance is not PASS/final_go')
    if full.get('pass') is not True: failures.append('dev19 strict aggregate did not pass')
    devices=full.get('results') or []
    if len(devices)!=3: failures.append(f'accepted 3-Android evidence expected 3 results, got {len(devices)}')
    aliases={str(r.get('device_alias')) for r in devices}; expected={'pixel-10-pro','pixel-7-pro','lenovo-tb-j606l'}
    if aliases!=expected: failures.append(f'dev19 device cohort mismatch: {sorted(aliases)}')
    for r in devices:
        alias=r.get('device_alias') or 'unknown'
        if r.get('pass') is not True: failures.append(f'{alias}: strict result not PASS')
        for required in ('G0_BUILD','G0_JSON_SELF_CONTAINED','G0_NO_SCREENSHOTS','G0_SNAPSHOT','G1_FROZEN_COHORT_COUNT','G2_ENVIRONMENT','G3_DURATION','G4_PEER_EXPIRE','G5_METRIC_UPTIME','G6_GEOMETRY_2D','G7_RECOVERY_BUDGET','G8_TIMING_HARD_BREACH','G9_END_STRATEGY','G10_FABRIC_TIMELINE_PRESENT','G10_EXPIRE_RECONSTRUCTION','G11_HUMAN_FLAGS'):
            g=gate(r,required)
            if not g or g.get('pass') is not True: failures.append(f'{alias}: {required} missing/FAIL')
        exp=gate(r,'G4_PEER_EXPIRE')
        if not exp or exp.get('observed')!=0: failures.append(f'{alias}: peer_expire_delta != 0')
        flags=(gate(r,'G11_HUMAN_FLAGS') or {}).get('observed') or {}
        if flags.get('human_scanning_enabled') is not False or flags.get('human_localization_validated') is not False or flags.get('rescue_use_validated') is not False:
            failures.append(f'{alias}: accepted dev19 human/rescue flags are not all false')
    report={'schema_version':1,'release':'dev-19','accepted_evidence_commit':'46995694e8841eaf383b0fc43ea72dc77aeef072',
            'release_tag_commit':'7d70bd3ac2cfc1bc8fe440be3b415120a6a69b43','baseline_regression':'PASS' if not failures else 'FAIL',
            'accepted_devices':sorted(aliases),'strict_result_count':len(devices),'files':{p.name:sha256(p) for p in sorted(d.iterdir()) if p.is_file()},
            'failures':failures,'final_go':not failures}
    if a.output:pathlib.Path(a.output).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2)); return 0 if not failures else 2
if __name__=='__main__':sys.exit(main())
