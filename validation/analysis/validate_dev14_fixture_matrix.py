#!/usr/bin/env python3
import json,pathlib,sys
from dev14_validation import timeline_errors,environment_errors,hard_gate_errors
root=pathlib.Path(__file__).resolve().parents[1]/'fixtures'/'dev14'; failures=[]; rows=[]
for f in sorted(root.glob('*.json')):
    raw=json.load(open(f)); exp=raw['expect']; d=raw['snapshot']; kind=exp['validator']; errs=[]
    if kind=='timeline': errs=timeline_errors(d)
    elif kind=='environment': errs=environment_errors(d)
    elif kind=='hard': errs=hard_gate_errors(d)
    elif kind=='interval_structure':
        errs=[e for e in environment_errors(d) if e.startswith('ENVIRONMENT_INTERVAL_') or e.startswith('DUPLICATE_OVERLAPPING')]
    elif kind=='history':
        if d.get('long_hash_before')!=d.get('long_hash_after') or d.get('export1_sha256')!=d.get('export2_sha256'): errs=['SNAPSHOT_IMMUTABILITY_FAILURE']
    passed=not errs; reason=exp.get('reason'); good=passed==exp['pass'] and (reason is None or errs==[reason])
    rows.append({'fixture':f.name,'pass_as_expected':good,'errors':errs});
    if not good: failures.append(rows[-1])
print(json.dumps({'pass':not failures,'fixtures':rows},indent=2)); sys.exit(0 if not failures else 1)
