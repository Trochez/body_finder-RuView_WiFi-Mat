#!/usr/bin/env python3
import argparse,json

def select(payload, run_id=None):
    run=payload.get('validation_run')
    if run_id and run and run.get('run_id')==run_id: return run
    if run_id:
        for key in ('completed_validation_runs','validation_runs'):
            for item in payload.get(key,[]) or []:
                if item.get('run_id')==run_id: return item
    return run

p=argparse.ArgumentParser()
p.add_argument('export1'); p.add_argument('export2'); p.add_argument('--run-id')
a=p.parse_args()
x=select(json.load(open(a.export1,encoding='utf-8')),a.run_id); y=select(json.load(open(a.export2,encoding='utf-8')),a.run_id)
if not x or not y: raise SystemExit('FAIL: selected validation_run missing')
if not x.get('snapshot_frozen') or not y.get('snapshot_frozen'): raise SystemExit('FAIL: snapshot_frozen must be true')
if x!=y:
    dif=[k for k in sorted(set(x)|set(y)) if x.get(k)!=y.get(k)]
    raise SystemExit('FAIL: completed validation snapshot drift: '+', '.join(dif))
print('PASS: completed validation snapshot is immutable for run_id='+str(x.get('run_id')))
