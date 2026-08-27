#!/usr/bin/env python3
from __future__ import annotations
from dev20_2_fusion import infer_fused_presence, canonical_result, PARAMETERS

def samples(center, n=100, disturb=False, start=1_000_000):
    out=[]
    for i in range(n):
        v=center + ((i%5)-2)*0.25
        if disturb:
            v += (3.5 if i%7 in (0,1,2) else -2.5 if i%11==0 else 0.0)
        out.append({'wall_ms':start+i*800,'rssi_dbm':v})
    return out

def topology(disturb=False, missing_node=False):
    nodes=['A','B','C']; b={}; o={}
    for a in nodes:
        if missing_node and a=='C': continue
        for p in nodes:
            if a==p: continue
            lid=f'{a}::{p}'; b[lid]=samples(-68-(ord(a)+ord(p))%3); o[lid]=samples(-68-(ord(a)+ord(p))%3,disturb=disturb)
    return b,o

def main():
    b,o=topology(False); r=infer_fused_presence(b,o,acquisition_health={'environment_valid':True,'baseline_regression_pass':True})
    assert r.prediction=='NO_HUMAN_EVIDENCE', r
    b,o=topology(True); r2=infer_fused_presence(b,o,acquisition_health={'environment_valid':True,'baseline_regression_pass':True})
    assert r2.prediction=='HUMAN_EVIDENCE', r2
    assert any(x['derivative_energy_change']>0 for x in r2.per_link_features)
    assert any(x['variance_ratio_change']>0 for x in r2.per_link_features)
    assert canonical_result(r2)==canonical_result(infer_fused_presence(b,o,acquisition_health={'environment_valid':True,'baseline_regression_pass':True}))
    b,o=topology(True,missing_node=True); r3=infer_fused_presence(b,o,acquisition_health={'environment_valid':True,'baseline_regression_pass':True})
    # two observer nodes are allowed; one observer only must fail closed
    b1={k:v for k,v in b.items() if k.startswith('A::')}; o1={k:v for k,v in o.items() if k.startswith('A::')}
    r4=infer_fused_presence(b1,o1,acquisition_health={'environment_valid':True,'baseline_regression_pass':True})
    assert r4.prediction=='INDETERMINATE'
    r5=infer_fused_presence(*topology(False),acquisition_health={'environment_valid':False,'baseline_regression_pass':True})
    assert r5.prediction=='INDETERMINATE'
    assert PARAMETERS['min_observer_nodes']==2
    print('DEV20_2_FUSION_TESTS_PASS')
if __name__=='__main__': main()
