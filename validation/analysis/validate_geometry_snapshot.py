#!/usr/bin/env python3
import json,sys
p=json.load(open(sys.argv[1],encoding='utf-8')); r=p.get('validation_run') or p
assert r.get('snapshot_frozen') is True
for k in ['geometry_at_end','fused_range_observations_at_end','graph_diagnostics_at_end']: assert k in r,k
print('PASS geometry snapshot')
