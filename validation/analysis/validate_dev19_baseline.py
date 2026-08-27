#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,pathlib,sys

def sha256(p:pathlib.Path)->str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--evidence-dir',default='evidence/dev-19/dev19-acceptance'); ap.add_argument('--output'); a=ap.parse_args()
    d=pathlib.Path(a.evidence_dir); failures=[]
    final=json.loads((d/'dev19-final-acceptance.json').read_text()); full=json.loads((d/'dev19-3android-acceptance.json').read_text())
    if not final.get('final_go'): failures.append('dev19 final_go is not true')
    if final.get('human_scanning_enabled') is not False: failures.append('dev19 human scanning baseline must remain false')
    if final.get('human_localization_validated') is not False: failures.append('dev19 localization baseline must remain false')
    if final.get('rescue_use_validated') is not False: failures.append('dev19 rescue baseline must remain false')
    devices=full.get('devices') or full.get('runs') or []
    if len(devices)<3: failures.append('accepted 3-Android evidence missing')
    for r in devices:
        vr=r.get('validation_run') if isinstance(r,dict) else None; vr=vr if isinstance(vr,dict) else r
        if isinstance(vr,dict) and vr.get('peer_expire_delta',0)!=0: failures.append(f"peer expiry regression: {r.get('device_alias') or r.get('device_id')}")
    report={'schema_version':1,'release':'dev-19','accepted_evidence_commit':'46995694e8841eaf383b0fc43ea72dc77aeef072',
            'release_tag_commit':'7d70bd3ac2cfc1bc8fe440be3b415120a6a69b43','baseline_regression':'PASS' if not failures else 'FAIL',
            'files':{p.name:sha256(p) for p in sorted(d.iterdir()) if p.is_file()},'failures':failures,'final_go':not failures}
    if a.output:pathlib.Path(a.output).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2)); return 0 if not failures else 2
if __name__=='__main__':sys.exit(main())
