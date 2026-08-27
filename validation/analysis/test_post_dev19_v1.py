#!/usr/bin/env python3
import pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from body_finder_v1_science import *

def test_presence():
    b={'a':[-60,-60,-61,-59,-60]*5,'b':[-70,-70,-71,-69,-70]*5,'c':[-65,-65,-66,-64,-65]*5}
    o={'a':[-52,-51,-53,-52,-51]*5,'b':[-62,-61,-63,-62,-61]*5,'c':[-58,-57,-59,-58,-57]*5}
    r=infer_presence(b,o,acquisition_health={'environment_valid':True,'baseline_regression_pass':True,'usable_metric_range_uptime_percent':95}); assert r.prediction=='HUMAN_EVIDENCE',r

def test_negative_indeterminate():
    b={'a':[-60]*20,'b':[-70]*20}; o={'a':[-60]*20,'b':[-70]*20}; assert infer_presence(b,o,acquisition_health={'environment_valid':True,'usable_metric_range_uptime_percent':100}).prediction=='NO_HUMAN_EVIDENCE'
    assert infer_presence({'a':[-60]*20},{'a':[-50]*20},acquisition_health={'environment_valid':True,'usable_metric_range_uptime_percent':100}).prediction=='INDETERMINATE'

def test_split_guard():
    try: enforce_split_policy([{'session_id':'x','split':'TRAIN'},{'session_id':'x','split':'TEST'}])
    except ValueError: pass
    else: raise AssertionError('leakage not rejected')

def test_rti_uncertainty():
    pos={'A':(0,0),'B':(4,0),'C':(0,4)}; eps={'ab':('A','B'),'ac':('A','C'),'bc':('B','C')}; f={k:{'normalized_change':3.0,'quality':1.0} for k in eps}; r=localize_rti(f,pos,eps); assert r.covariance_2x2 is not None; assert r.localization_tier in ('USABLE','COARSE','PRESENCE_ONLY')

def test_tracking_cluster():
    out=track_localizations([{'detections':[{'x_m':0,'y_m':0}]},{'detections':[{'x_m':.2,'y_m':.1}]},{'unresolved_multi_target':True,'detections':[{'x_m':1,'y_m':1},{'x_m':1.2,'y_m':1.1}]}]); assert any(x['state']=='POSSIBLE_CLUSTER' for x in out['timeline'])

def test_capability_truth():
    assert capability_truth_from_probe({'modality':'CSI','api_supported':True,'functional_probe_attempted':True,'real_sample_count':0})['state']=='SUPPORTED_UNVERIFIED'
    assert capability_truth_from_probe({'modality':'RTT','api_supported':True,'functional_probe_attempted':True,'real_sample_count':2})['state']=='VERIFIED_REAL'

def test_v1_fail_closed():
    reports={k:{'baseline_regression':'PASS','physical_acceptance':'PASS'} for k in ('dev19','dev20','dev21','dev22','dev23','dev24')}; assert aggregate_v1_reports(reports)['final_go'] is True
    reports['dev20']['physical_acceptance']='FAIL'; assert aggregate_v1_reports(reports)['final_go'] is False

def main():
    for f in [test_presence,test_negative_indeterminate,test_split_guard,test_rti_uncertainty,test_tracking_cluster,test_capability_truth,test_v1_fail_closed]: f()
    print('post-dev19-v1 tests: PASS')
if __name__=='__main__':main()
