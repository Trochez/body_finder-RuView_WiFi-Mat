#!/usr/bin/env python3
import argparse,json,pathlib,sys
p=argparse.ArgumentParser();p.add_argument('files',nargs='+');p.add_argument('--output');a=p.parse_args();items=[];ok=True
for f in a.files:
 d=json.loads(pathlib.Path(f).read_text());reasons=[]
 if d.get('evidence_class')!='PRE_RUN_DIAGNOSTIC_V1':reasons.append('WRONG_EVIDENCE_CLASS')
 if d.get('acceptance_eligible') is not False:reasons.append('DIAGNOSTIC_MUST_NOT_BE_ACCEPTANCE_ELIGIBLE')
 if not isinstance(d.get('blocking_reasons'),list):reasons.append('BLOCKING_REASONS_MISSING')
 if d.get('diagnostic_read_only') is not True:reasons.append('DIAGNOSTIC_MUTATION_GUARD_FAILED')
 items.append({'file':f,'status':'PASS' if not reasons else 'FAIL','reasons':reasons});ok&=not reasons
out={'schema':'pre-run-diagnostic-validator-v1','release':'dev-20.13','status':'PASS' if ok else 'FAIL','acceptance_evidence':False,'items':items};txt=json.dumps(out,indent=2)+'\n';pathlib.Path(a.output).write_text(txt) if a.output else print(txt,end='');sys.exit(0 if ok else 2)
