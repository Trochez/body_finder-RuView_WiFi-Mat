#!/usr/bin/env python3
import json, sys
from pathlib import Path

UNFILTERED_WINDOW_MS=10000
PROBE_WINDOW_MS=15000
TRIGGERS={'FULL_COHORT_STALL','PEER_STARVATION'}

def evaluate(c):
    s=c.get('strategy'); mode=c.get('filter_mode'); count=c.get('hardware_filter_count',0)
    if s=='FILTERED_PRIMARY': return mode=='MANUFACTURER_FILTERED' and count>0
    if s=='UNFILTERED_RECOVERY':
        g=c.get('active_recovery_generation'); sg=c.get('strategy_recovery_generation'); started=c.get('recovery_started_wall_ms')
        return g is not None and sg is not None and g==sg and c.get('trigger_kind') in TRIGGERS and started is not None and c.get('now_wall_ms',0)-started<=UNFILTERED_WINDOW_MS and mode=='UNFILTERED' and count==0
    if s=='FILTERED_RECOVERY_PROBE':
        g=c.get('active_recovery_generation'); sg=c.get('strategy_recovery_generation')
        return g is not None and sg is not None and g==sg and c.get('trigger_kind') in TRIGGERS and c.get('now_wall_ms',0)-c.get('strategy_since_wall_ms',0)<=PROBE_WINDOW_MS and mode=='MANUFACTURER_FILTERED' and count>0
    return False

def main(paths):
    if not paths: paths=sorted(str(p) for p in Path('validation/fixtures/dev13').glob('*.json'))
    results=[]; ok=True
    for path in paths:
        d=json.load(open(path)); actual=evaluate(d); expected=d.get('expected_valid') is True; passed=actual==expected; ok &= passed
        results.append({'file':path,'expected_valid':expected,'actual_valid':actual,'pass':passed})
    print(json.dumps({'results':results,'pass':ok},indent=2)); return 0 if ok else 1
if __name__=='__main__': raise SystemExit(main(sys.argv[1:]))
