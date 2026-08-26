#!/usr/bin/env python3
from pathlib import Path
import copy,json,shutil
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'validation/fixtures/dev16'
if OUT.exists(): shutil.rmtree(OUT)
(OUT/'campaign').mkdir(parents=True); (OUT/'boundaries').mkdir(parents=True)

def events(unfiltered=0,probe=0,targeted=False):
    if unfiltered<=0: return []
    peer='peer-b'; trig='PEER_STARVATION' if targeted else 'FULL_COHORT_STALL'; w=1_000_000
    return [
      {'seq':1,'type':'RECOVERY_REQUESTED','wall_ms':w,'recovery_generation':1,'trigger_kind':trig,'trigger_peer_id':peer if targeted else None,'peer_id':peer if targeted else None},
      {'seq':2,'type':'FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY','wall_ms':w+min(100,unfiltered-1),'recovery_generation':1,'trigger_kind':trig,'trigger_peer_id':peer if targeted else None,'peer_id':peer},
      {'seq':3,'type':'RECOVERY_SUCCESS','wall_ms':w+unfiltered,'recovery_generation':1,'trigger_kind':trig,'trigger_peer_id':peer if targeted else None,'peer_id':peer},
      {'seq':4,'type':'ACQUISITION_STRATEGY_CHANGED','wall_ms':w+unfiltered,'recovery_generation':1,'from_strategy':'UNFILTERED_RECOVERY','to_strategy':'FILTERED_RECOVERY_PROBE'},
      {'seq':5,'type':'ACQUISITION_STRATEGY_CHANGED','wall_ms':w+unfiltered+probe,'recovery_generation':1,'from_strategy':'FILTERED_RECOVERY_PROBE','to_strategy':'FILTERED_PRIMARY'},
    ]

def rolling_max(es):
    xs=sorted(e['wall_ms'] for e in es if e['type']=='RECOVERY_REQUESTED')
    return max((sum(1 for x in xs if t<=x<=t+300000) for t in xs),default=0)

def make(run_id='run-long',stage='LONG_1',device='pixel-7-pro',short=False,unfiltered=0,probe=0,targeted=False):
    es=events(unfiltered,probe,targeted); elapsed=60000 if short else 330000; start=900000; end=start+elapsed
    roll=rolling_max(es)
    run={'snapshot_schema_version':4,'snapshot_frozen':True,'run_id':run_id,'started_wall_ms':start,'ended_wall_ms':end,'snapshot_wall_ms':end,'snapshot_elapsed_ms':elapsed,'elapsed_ms':elapsed,'acceptance_minimum_ms':300000,'acceptance_duration_eligible':not short,'short_diagnostic_run':short,
      'preflight_at_start':{'ready':True,'acquisition_strategy':'FILTERED_PRIMARY','hardware_filter_count':1},
      'environment':{'valid':True,'violation_count':0,'violation_types':[],'unauthorized_strategy_violation_count':0},'environment_violation_events':[],
      'validation_counters':{'peer_expire_delta':0,'recovery_attempt_delta':len([e for e in es if e['type']=='RECOVERY_REQUESTED']),'recovery_first_valid_callback_delta':len([e for e in es if e['type']=='FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY']),'peer_starvation_recovery_request_delta':1 if targeted else 0,'peer_starvation_recovery_success_delta':1 if targeted else 0,'peer_starvation_recovery_failure_delta':0},
      'acquisition_state_at_end':{'logical_acquisition_strategy':'FILTERED_PRIMARY','active_recovery_generation':None,'strategy_recovery_generation':None,'recovery_unfiltered_hard_limit_ms':10000,'recovery_unfiltered_action_target_ms':9500,'filtered_probe_exit_target_ms':14500,'filtered_probe_hard_limit_ms':15000,'filtered_probe_action_target_ms':14000,'recovery_budget_window_ms':300000,'recovery_budget_limit':3,'recovery_attempt_delta_total':len([e for e in es if e['type']=='RECOVERY_REQUESTED']),'recovery_attempts_in_current_5min_window_at_end':roll,'recovery_attempts_max_in_any_rolling_5min_window':roll},
      'recovery_timing_summary':{'generation_count':1 if es else 0,'max_unfiltered_duration_ms':unfiltered,'unfiltered_action_target_miss_count':1 if 9500<unfiltered<=10000 else 0,'unfiltered_hard_limit_breach_count':1 if unfiltered>10000 else 0,'max_filtered_probe_duration_ms':probe,'filtered_probe_target_miss_count':1 if 14500<probe<=15000 else 0,'filtered_probe_hard_limit_breach_count':1 if probe>15000 else 0},
      'single_remote_peer_metric_uptime_percent':99.0,'all_expected_peer_metric_uptime_percent':95.0,'geometry_2d_uptime_percent':95.0,'per_peer_at_end':[],'system_ranging_at_end':{'state':'FIXTURE'},'events':es,'geometry_at_end':None,'fused_range_observations_at_end':[],'snapshot_identity_sha256':'fixture'}
    source=run_id if stage!='SHORT' else ('p7-long' if device=='pixel-7-pro' else 'p10-long')
    return {'build':'0.2.0-experimental.16','protocol_version':2,'json_self_contained':True,'screenshots_required':False,'manual_geometry_override':False,'human_scanning_enabled':False,'human_localization_validated':False,'rescue_use_validated':False,'evidence_contract':{'schema':'dev16-self-contained-json-evidence-v4'},'export_metadata':{'device_alias':device,'run_id':run_id,'snapshot_stage':stage,'source_long_run_id':source},'validation_run':run}

def dump(path,obj): path.write_text(json.dumps(obj,indent=2)+'\n')
# Directed campaign: targeted recovery only on Pixel 7, proving aggregate semantics.
for dev,longid,targeted in [('pixel-7-pro','p7-long',True),('pixel-10-pro','p10-long',False)]:
    base=make(longid,'LONG_1',dev,False,200,14500,targeted)
    dump(OUT/'campaign'/f'{dev}-long1.json',base)
    b=copy.deepcopy(base); b['export_metadata']['snapshot_stage']='LONG_2'; dump(OUT/'campaign'/f'{dev}-long2.json',b)
    sh=make(f'{dev}-short','SHORT',dev,True); sh['export_metadata']['source_long_run_id']=longid; dump(OUT/'campaign'/f'{dev}-short.json',sh)
    b=copy.deepcopy(base); b['export_metadata']['snapshot_stage']='LONG_POST_SHORT'; dump(OUT/'campaign'/f'{dev}-long-postshort.json',b)
# Boundaries.
for d in [9499,9500,9501,9999,10000,10001,10148]: dump(OUT/'boundaries'/f'unfiltered-{d}.json',make(f'u{d}','LONG_1','fixture',False,d,14500,False))
for d in [13999,14000,14001,14500,14501,14999,15000,15001]: dump(OUT/'boundaries'/f'probe-{d}.json',make(f'p{d}','LONG_1','fixture',False,200,d,False))
# State/missing-field negatives.
x=make('failed-safe','LONG_1','fixture'); x['validation_run']['acquisition_state_at_end']['logical_acquisition_strategy']='FAILED_SAFE'; dump(OUT/'boundaries'/'long-ended-failed-safe.json',x)
x=make('active-probe','LONG_1','fixture'); x['validation_run']['acquisition_state_at_end']['logical_acquisition_strategy']='FILTERED_RECOVERY_PROBE'; x['validation_run']['acquisition_state_at_end']['active_recovery_generation']=7; x['validation_run']['acquisition_state_at_end']['strategy_recovery_generation']=7; dump(OUT/'boundaries'/'long-ended-active-probe.json',x)
x=make('missing-field','LONG_1','fixture'); del x['validation_run']['acquisition_state_at_end']['filtered_probe_exit_target_ms']; dump(OUT/'boundaries'/'missing-acquisition-field.json',x)
# Rolling budget positive/negative, directly from event request timestamps (failure/success paths are not required for this isolated budget fixture metadata).
def budget_case(name,walls,expected):
    x=make(name,'LONG_1','fixture'); es=[]; seq=1
    for g,w in enumerate(walls,1): es += [{'seq':seq,'type':'RECOVERY_REQUESTED','wall_ms':w,'recovery_generation':g,'trigger_kind':'FULL_COHORT_STALL'},{'seq':seq+1,'type':'RECOVERY_FAILURE','wall_ms':w+100,'recovery_generation':g,'trigger_kind':'FULL_COHORT_STALL'},{'seq':seq+2,'type':'ACQUISITION_STRATEGY_CHANGED','wall_ms':w+100,'recovery_generation':g,'from_strategy':'UNFILTERED_RECOVERY','to_strategy':'FILTERED_RECOVERY_PROBE'},{'seq':seq+3,'type':'ACQUISITION_STRATEGY_CHANGED','wall_ms':w+14600,'recovery_generation':g,'from_strategy':'FILTERED_RECOVERY_PROBE','to_strategy':'FILTERED_PRIMARY'}]; seq+=4
    x['validation_run']['events']=es; r=rolling_max(es); x['validation_run']['acquisition_state_at_end']['recovery_attempt_delta_total']=len(walls); x['validation_run']['acquisition_state_at_end']['recovery_attempts_max_in_any_rolling_5min_window']=r; x['validation_run']['recovery_timing_summary'].update({'generation_count':len(walls),'max_unfiltered_duration_ms':100,'max_filtered_probe_duration_ms':14500}); x['fixture_expected']=expected; dump(OUT/'boundaries'/f'{name}.json',x)
budget_case('four-total-max-rolling-three',[0,100000,200000,400001],'PASS')
budget_case('four-in-rolling-five-min',[0,100000,200000,300000],'FAIL')
print('DEV16_FIXTURES_GENERATED')
