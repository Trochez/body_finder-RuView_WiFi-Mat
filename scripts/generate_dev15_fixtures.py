#!/usr/bin/env python3
from __future__ import annotations
import copy,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; FIX=ROOT/'validation/fixtures/dev15'
for sub in ('campaign','corrupted'): (FIX/sub).mkdir(parents=True,exist_ok=True)
devices={'pixel-10-pro':('Google','Pixel 10 Pro','node-pixel10'),'pixel-7-pro':('Google','Pixel 7 Pro','node-pixel7'),'lenovo-tb-j606l':('Lenovo','TB-J606L','node-lenovo')}
distances={tuple(sorted(('node-pixel10','node-pixel7'))):3.10,tuple(sorted(('node-pixel10','node-lenovo'))):3.20,tuple(sorted(('node-pixel7','node-lenovo'))):1.85}
gt={'schema':'body-finder-ground-truth-distances-v1','units':'m','method':'tape','ground_truth_entered_into_app':False,'pairs_m':[{'a':'pixel-10-pro','b':'pixel-7-pro','distance_m':3.07},{'a':'pixel-10-pro','b':'lenovo-tb-j606l','distance_m':3.23},{'a':'pixel-7-pro','b':'lenovo-tb-j606l','distance_m':1.83}]}
def observations(node):
    out=[]
    for pair,distance in distances.items():
        if node in pair:
            peer=pair[1] if pair[0]==node else pair[0]; out.append({'observer_node_id':node,'peer_node_id':peer,'distance_m':distance})
    return out
def long_run(alias,node):
    peers=[x[2] for key,x in devices.items() if key!=alias]; target=peers[0]; start=1_000_000
    events=[
      {'seq':1,'wall_ms':start+1000,'elapsed_ms':1000,'elapsed_from_run_start_ms':1000,'type':'RECOVERY_REQUESTED','recovery_generation':1,'peer_id':target,'trigger_kind':'PEER_STARVATION','trigger_peer_id':target},
      {'seq':2,'wall_ms':start+1001,'elapsed_ms':1001,'elapsed_from_run_start_ms':1001,'type':'ACQUISITION_STRATEGY_CHANGED','recovery_generation':1,'from_strategy':'FILTERED_PRIMARY','to_strategy':'UNFILTERED_RECOVERY'},
      {'seq':3,'wall_ms':start+2000,'elapsed_ms':2000,'elapsed_from_run_start_ms':2000,'type':'FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY','recovery_generation':1,'peer_id':target,'trigger_kind':'PEER_STARVATION','trigger_peer_id':target},
      {'seq':4,'wall_ms':start+3000,'elapsed_ms':3000,'elapsed_from_run_start_ms':3000,'type':'RECOVERY_SUCCESS','recovery_generation':1,'peer_id':target,'trigger_kind':'PEER_STARVATION','trigger_peer_id':target},
      {'seq':5,'wall_ms':start+3001,'elapsed_ms':3001,'elapsed_from_run_start_ms':3001,'type':'ACQUISITION_STRATEGY_CHANGED','recovery_generation':1,'from_strategy':'UNFILTERED_RECOVERY','to_strategy':'FILTERED_RECOVERY_PROBE'},
      {'seq':6,'wall_ms':start+17000,'elapsed_ms':17000,'elapsed_from_run_start_ms':17000,'type':'ACQUISITION_STRATEGY_CHANGED','recovery_generation':1,'from_strategy':'FILTERED_RECOVERY_PROBE','to_strategy':'FILTERED_PRIMARY'}]
    per=[]
    for pid in peers:
        hit=int(pid==target); per.append({'node_id':pid,'run_starvation_recovery_participation_count':hit,'run_first_callback_after_recovery_count':hit,'run_starvation_recovery_success_count':hit,'run_starvation_recovery_failure_count':0,'acquisition':{'run_first_callback_after_recovery_count':hit}})
    return {'run_id':f'{alias}-long-run','started_wall_ms':start,'ended_wall_ms':start+330000,'elapsed_ms':330000,'snapshot_schema_version':3,'snapshot_frozen':True,'acceptance_duration_eligible':True,'short_diagnostic_run':False,'preflight_at_start':{'ready':True,'acquisition_strategy':'FILTERED_PRIMARY','hardware_filter_count':1},'environment':{'valid':True,'violation_count':0,'violation_types':[],'unauthorized_strategy_violation_count':0},'environment_violation_events':[],'usable_metric_range_uptime_percent':99.0,'geometry_2d_uptime_percent':99.0,'validation_counters':{'peer_expire_delta':0,'recovery_attempt_delta':1,'peer_starvation_recovery_request_delta':1,'recovery_first_valid_callback_delta':1,'peer_starvation_recovery_success_delta':1,'peer_starvation_recovery_failure_delta':0},'acquisition_state_at_end':{'logical_acquisition_strategy':'FILTERED_PRIMARY','recovery_attempts_in_current_5min_window':1,'filtered_probe_window_ms':15000,'filtered_probe_exit_target_ms':14500},'per_peer_at_end':per,'events':events,'fused_range_observations_at_end':observations(node)}
def short_run(alias,node):
    peers=[x[2] for key,x in devices.items() if key!=alias]; start=2_000_000
    return {'run_id':f'{alias}-short-run','started_wall_ms':start,'ended_wall_ms':start+60000,'elapsed_ms':60000,'snapshot_schema_version':3,'snapshot_frozen':True,'acceptance_duration_eligible':False,'short_diagnostic_run':True,'preflight_at_start':{'ready':True,'acquisition_strategy':'FILTERED_PRIMARY','hardware_filter_count':1},'environment':{'valid':True,'violation_count':0,'violation_types':[],'unauthorized_strategy_violation_count':0},'environment_violation_events':[],'usable_metric_range_uptime_percent':99.0,'geometry_2d_uptime_percent':99.0,'validation_counters':{'peer_expire_delta':0,'recovery_attempt_delta':0,'peer_starvation_recovery_request_delta':0,'recovery_first_valid_callback_delta':0,'peer_starvation_recovery_success_delta':0,'peer_starvation_recovery_failure_delta':0},'acquisition_state_at_end':{'logical_acquisition_strategy':'FILTERED_PRIMARY','recovery_attempts_in_current_5min_window':0,'filtered_probe_window_ms':15000,'filtered_probe_exit_target_ms':14500},'per_peer_at_end':[{'node_id':pid,'run_starvation_recovery_participation_count':0,'run_first_callback_after_recovery_count':0,'run_starvation_recovery_success_count':0,'run_starvation_recovery_failure_count':0,'acquisition':{'run_first_callback_after_recovery_count':0}} for pid in peers],'events':[],'fused_range_observations_at_end':observations(node)}
def export_doc(alias,manufacturer,model,node,run,stage,seq,source):
    filename=f"{alias}-{run['run_id'][:8]}-{stage.lower().replace('_','-')}.json"
    return {'report_version':17,'generated_at':'2026-08-25T10:00:00Z','app':'Body Finder – RuView','build':'0.2.0-experimental.15','protocol_version':2,'json_self_contained':True,'screenshots_required':False,'manual_geometry_override':False,'human_scanning_enabled':False,'human_localization_validated':False,'rescue_use_validated':False,'node_id':node,'export_metadata':{'device_alias':alias,'device_manufacturer':manufacturer,'device_model':model,'node_id':node,'run_id':run['run_id'],'run_type':'SHORT' if stage=='SHORT' else 'LONG','snapshot_stage':stage,'elapsed_ms':run['elapsed_ms'],'snapshot_frozen':run['snapshot_frozen'],'source_long_run_id':source,'export_sequence':seq,'generated_at':'2026-08-25T10:00:00Z','build':'0.2.0-experimental.15','protocol_version':2,'suggested_filename':filename},'validation_run':run}
campaign={}
for alias,(manufacturer,model,node) in devices.items():
    lr=long_run(alias,node); sr=short_run(alias,node); docs={'LONG_1':export_doc(alias,manufacturer,model,node,lr,'LONG_1',1,lr['run_id']),'LONG_2':export_doc(alias,manufacturer,model,node,lr,'LONG_2',2,lr['run_id']),'SHORT':export_doc(alias,manufacturer,model,node,sr,'SHORT',1,lr['run_id']),'LONG_POST_SHORT':export_doc(alias,manufacturer,model,node,lr,'LONG_POST_SHORT',3,lr['run_id'])}; campaign[alias]=docs
    for stage,doc in docs.items(): (FIX/'campaign'/f"{alias}-{stage.lower().replace('_','-')}.json").write_text(json.dumps(doc,indent=2)+'\n')
(FIX/'campaign'/'ground-truth.json').write_text(json.dumps(gt,indent=2)+'\n')
base=campaign['pixel-10-pro']['LONG_1']; corruptions={}
x=copy.deepcopy(base); del x['validation_run']['usable_metric_range_uptime_percent']; corruptions['missing-required-field.json']=('MISSING_REQUIRED_FIELD',x)
x=copy.deepcopy(base); x['validation_run']['events'][2]['peer_id']='wrong-peer'; corruptions['wrong-peer.json']=('FIRST_VALID_WRONG_TARGET',x)
x=copy.deepcopy(base); x['validation_run']['validation_counters']['recovery_first_valid_callback_delta']=0; corruptions['counter-mismatch.json']=('RECOVERY_COUNTER_EVENT_MISMATCH',x)
x=copy.deepcopy(base); x['validation_run']['per_peer_at_end'][0]['acquisition']['run_first_callback_after_recovery_count']=0; corruptions['nested-counter-mismatch.json']=('RECOVERY_COUNTER_EVENT_MISMATCH',x)
x=copy.deepcopy(base); x['validation_run']['acquisition_state_at_end']['logical_acquisition_strategy']='FAILED_SAFE'; corruptions['failed-safe-at-end.json']=('FAILED_SAFE_AT_END',x)
x=copy.deepcopy(base); x['validation_run']['events'][5]['wall_ms']=x['validation_run']['events'][4]['wall_ms']+15001; x['validation_run']['events'][5]['elapsed_ms']=18002; x['validation_run']['events'][5]['elapsed_from_run_start_ms']=18002; corruptions['probe-expired.json']=('FILTERED_PROBE_HARD_LIMIT_EXCEEDED',x)
for name,(expected,doc) in corruptions.items(): doc['expected_error']=expected; (FIX/'corrupted'/name).write_text(json.dumps(doc,indent=2)+'\n')
print('DEV15_FIXTURES_GENERATED')
