#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, pathlib, sys

def load(p):return json.loads(pathlib.Path(p).read_text(encoding='utf-8'))
def stable_sha(o):return hashlib.sha256(json.dumps(o,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def verify_smoke(d):
 s=d.get('validator_signature'); c=dict(d);c.pop('validator_signature',None);return bool(d.get('final_go')) and d.get('release')=='dev-20.4' and s=='sha256:'+stable_sha(c)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--smoke-go',required=True);ap.add_argument('--manifest',required=True);ap.add_argument('--output',required=True);a=ap.parse_args();sm=load(a.smoke_go)
 if not verify_smoke(sm):raise SystemExit('BLOCKED: valid signed dev-20.4 smoke-go-no-go.json with final_go=true is required')
 m=load(a.manifest);sessions=m.get('sessions') or []
 if len(sessions)!=54:raise SystemExit(f'final campaign requires exactly 54 fresh JSON exports, got {len(sessions)}')
 out={'schema_version':4,'release':'dev-20.4','evidence_contract':'dev20.4-self-contained-json-evidence-v7','smoke_gate_signature':sm['validator_signature'],'campaign_id':m.get('campaign_id'),'sessions':sessions,'ground_truth_external_to_inference':True,'test_frozen':True,'screenshots_required':False}
 pathlib.Path(a.output).write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({'output':a.output,'sessions':len(sessions),'smoke_gate':'PASS'}));return 0
if __name__=='__main__':sys.exit(main())
