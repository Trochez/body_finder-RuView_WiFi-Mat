#!/usr/bin/env python3
import argparse, json, pathlib, sys


def validate(data):
    errors=[]
    t=data.get('thresholds',{})
    nodes=data.get('nodes',[])
    if data.get('status')!='APPROVED_EXPERIMENTAL_3NODE': errors.append('baseline status is not approved')
    if len(nodes)!=3: errors.append(f'expected 3 nodes, got {len(nodes)}')
    for n in nodes:
        name=n.get('device','unknown')
        def need(cond,msg):
            if not cond: errors.append(f'{name}: {msg}')
        need(n.get('expected_peers')==2,'expected_peers != 2')
        need(n.get('preflight_ready') is True,'preflight not ready')
        need(n.get('environment_valid') is True,'environment invalid')
        need(float(n.get('metric_uptime_percent',0))>=float(t.get('metric_uptime_percent_min',90)),'metric uptime regression')
        need(float(n.get('geometry_2d_uptime_percent',0))>=float(t.get('geometry_2d_uptime_percent_min',90)),'Geometry2D uptime regression')
        need(int(n.get('peer_expire_delta',999))<=int(t.get('peer_expire_delta_max',0)),'peer_expire_delta regression')
        need(int(n.get('max_recoveries_rolling_5min',999))<=int(t.get('recoveries_rolling_5min_max',3)),'recovery budget regression')
        need(int(n.get('hard_timing_breach',999))<=int(t.get('hard_timing_breach_max',0)),'hard timing breach')
        need(n.get('final_state')=='FILTERED_PRIMARY','final state is not FILTERED_PRIMARY')
        need(n.get('active_recovery_at_end') is False,'recovery active at end')
    return errors


def main():
    p=argparse.ArgumentParser()
    p.add_argument('baseline')
    p.add_argument('--output')
    a=p.parse_args()
    data=json.load(open(a.baseline,encoding='utf-8'))
    errors=validate(data)
    report={'schema_version':1,'gate':'dev17_frozen_baseline','pass':not errors,'error_count':len(errors),'errors':errors,'devices':[n.get('device') for n in data.get('nodes',[])]}
    text=json.dumps(report,indent=2)+'\n'
    if a.output: pathlib.Path(a.output).write_text(text,encoding='utf-8')
    print(text,end='')
    return 0 if not errors else 2

if __name__=='__main__': sys.exit(main())
