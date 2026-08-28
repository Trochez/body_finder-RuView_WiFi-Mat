#!/usr/bin/env python3
from dev20_3_detector import infer_fused_presence, canonical_result, PARAMETERS, ALGORITHM_VERSION, PARAMETER_HASH

def samples(center,n=100,disturb=False,start=1_000_000):
 out=[]
 for i in range(n):
  v=center+((i%5)-2)*.25
  if disturb:v += (4.5 if i%7 in (0,1,2) else -3.5 if i%11==0 else 0)
  out.append({'wall_ms':start+i*800,'rssi_dbm':v})
 return out

def topo(disturb=False):
 b={};o={};nodes='ABC'
 for a in nodes:
  for z in nodes:
   if a==z:continue
   k=f'{a}::{z}';b[k]=samples(-68-(ord(a)+ord(z))%3);o[k]=samples(-68-(ord(a)+ord(z))%3,disturb=disturb)
 return b,o

def main():
 b,o=topo(False);r=infer_fused_presence(b,o,acquisition_health={'environment_valid':True,'baseline_regression_pass':True});assert r.prediction in ('NO_HUMAN_EVIDENCE','INDETERMINATE')
 r2=infer_fused_presence(*topo(True),acquisition_health={'environment_valid':True,'baseline_regression_pass':True});assert r2.prediction=='HUMAN_EVIDENCE',r2
 assert canonical_result(r2)==canonical_result(infer_fused_presence(*topo(True),acquisition_health={'environment_valid':True,'baseline_regression_pass':True}))
 b,o=topo(True);b.pop('C::A');o.pop('C::A');assert infer_fused_presence(b,o,acquisition_health={'environment_valid':True,'baseline_regression_pass':True}).prediction=='INDETERMINATE'
 assert infer_fused_presence(*topo(True),acquisition_health={'environment_valid':False,'baseline_regression_pass':True}).prediction=='INDETERMINATE'
 assert PARAMETERS['min_observer_nodes']==3 and PARAMETERS['min_physical_baselines']==3 and ALGORITHM_VERSION.endswith('v3') and len(PARAMETER_HASH)==64
 print('DEV20_3_CANONICAL_TESTS_PASS')
if __name__=='__main__':main()
