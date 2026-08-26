#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "validation/analysis/dev15_validation.py"
GEN = ROOT / "scripts/generate_dev15_fixtures.py"
DOCS = ROOT / "docs/TESTING_DEV15.md"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f"patch anchor not found: {label}")
    return text.replace(old, new, 1)

# The global FIRST_VALID counter covers every accepted recovery generation,
# while per-peer starvation counters cover only PEER_STARVATION generations.
v = VALIDATOR.read_text()
old = '''        trigger = req[0].get("trigger_kind")
        target = req[0].get("trigger_peer_id") or req[0].get("peer_id")
        if trigger == "PEER_STARVATION":
'''
new = '''        if first:
            totals["first"] += 1
        trigger = req[0].get("trigger_kind")
        target = req[0].get("trigger_peer_id") or req[0].get("peer_id")
        if trigger == "PEER_STARVATION":
'''
v = replace_once(v, old, new, "global first-valid semantics")
v = v.replace('''                if first:
                    totals["first"] += 1; peer_totals[target]["first"] += 1
''','''                if first:
                    peer_totals[target]["first"] += 1
''',1)
VALIDATOR.write_text(v)

# Synthetic fixtures must mirror the real exported telemetry that hard gates use.
g = GEN.read_text()
old = '''    for pid in peers:
        hit=int(pid==target); per.append({'node_id':pid,'run_starvation_recovery_participation_count':hit,'run_first_callback_after_recovery_count':hit,'run_starvation_recovery_success_count':hit,'run_starvation_recovery_failure_count':0})
    return {'run_id':f'{alias}-long-run','started_wall_ms':start,'ended_wall_ms':start+330000,'elapsed_ms':330000,'snapshot_schema_version':3,'snapshot_frozen':True,'acceptance_duration_eligible':True,'short_diagnostic_run':False,'preflight_at_start':{'ready':True,'acquisition_strategy':'FILTERED_PRIMARY','hardware_filter_count':1},'environment':{'valid':True,'violation_count':0,'violation_types':[],'unauthorized_strategy_violation_count':0},'environment_violation_events':[],'usable_metric_range_uptime_percent':99.0,'geometry_2d_uptime_percent':99.0,'validation_counters':{'peer_expire_delta':0,'recovery_attempt_delta':1,'peer_starvation_recovery_request_delta':1,'recovery_first_valid_callback_delta':1,'peer_starvation_recovery_success_delta':1,'peer_starvation_recovery_failure_delta':0},'acquisition_state_at_end':{'recovery_attempts_in_current_5min_window':1,'filtered_probe_window_ms':15000,'filtered_probe_exit_target_ms':14500},'per_peer_at_end':per,'events':events,'fused_range_observations_at_end':observations(node)}
'''
new = '''    for pid in peers:
        hit=int(pid==target); per.append({'node_id':pid,'run_starvation_recovery_participation_count':hit,'run_first_callback_after_recovery_count':hit,'run_starvation_recovery_success_count':hit,'run_starvation_recovery_failure_count':0,'acquisition':{'run_first_callback_after_recovery_count':hit}})
    return {'run_id':f'{alias}-long-run','started_wall_ms':start,'ended_wall_ms':start+330000,'elapsed_ms':330000,'snapshot_schema_version':3,'snapshot_frozen':True,'acceptance_duration_eligible':True,'short_diagnostic_run':False,'preflight_at_start':{'ready':True,'acquisition_strategy':'FILTERED_PRIMARY','hardware_filter_count':1},'environment':{'valid':True,'violation_count':0,'violation_types':[],'unauthorized_strategy_violation_count':0},'environment_violation_events':[],'usable_metric_range_uptime_percent':99.0,'geometry_2d_uptime_percent':99.0,'validation_counters':{'peer_expire_delta':0,'recovery_attempt_delta':1,'peer_starvation_recovery_request_delta':1,'recovery_first_valid_callback_delta':1,'peer_starvation_recovery_success_delta':1,'peer_starvation_recovery_failure_delta':0},'acquisition_state_at_end':{'logical_acquisition_strategy':'FILTERED_PRIMARY','recovery_attempts_in_current_5min_window':1,'filtered_probe_window_ms':15000,'filtered_probe_exit_target_ms':14500},'per_peer_at_end':per,'events':events,'fused_range_observations_at_end':observations(node)}
'''
g = replace_once(g, old, new, "long fixture telemetry")
old = '''    return {'run_id':f'{alias}-short-run','started_wall_ms':start,'ended_wall_ms':start+60000,'elapsed_ms':60000,'snapshot_schema_version':3,'snapshot_frozen':True,'acceptance_duration_eligible':False,'short_diagnostic_run':True,'preflight_at_start':{'ready':True,'acquisition_strategy':'FILTERED_PRIMARY','hardware_filter_count':1},'environment':{'valid':True,'violation_count':0,'violation_types':[],'unauthorized_strategy_violation_count':0},'environment_violation_events':[],'usable_metric_range_uptime_percent':99.0,'geometry_2d_uptime_percent':99.0,'validation_counters':{'peer_expire_delta':0,'recovery_attempt_delta':0,'peer_starvation_recovery_request_delta':0,'recovery_first_valid_callback_delta':0,'peer_starvation_recovery_success_delta':0,'peer_starvation_recovery_failure_delta':0},'acquisition_state_at_end':{'recovery_attempts_in_current_5min_window':0,'filtered_probe_window_ms':15000,'filtered_probe_exit_target_ms':14500},'per_peer_at_end':[{'node_id':pid,'run_starvation_recovery_participation_count':0,'run_first_callback_after_recovery_count':0,'run_starvation_recovery_success_count':0,'run_starvation_recovery_failure_count':0} for pid in peers],'events':[],'fused_range_observations_at_end':observations(node)}
'''
new = '''    return {'run_id':f'{alias}-short-run','started_wall_ms':start,'ended_wall_ms':start+60000,'elapsed_ms':60000,'snapshot_schema_version':3,'snapshot_frozen':True,'acceptance_duration_eligible':False,'short_diagnostic_run':True,'preflight_at_start':{'ready':True,'acquisition_strategy':'FILTERED_PRIMARY','hardware_filter_count':1},'environment':{'valid':True,'violation_count':0,'violation_types':[],'unauthorized_strategy_violation_count':0},'environment_violation_events':[],'usable_metric_range_uptime_percent':99.0,'geometry_2d_uptime_percent':99.0,'validation_counters':{'peer_expire_delta':0,'recovery_attempt_delta':0,'peer_starvation_recovery_request_delta':0,'recovery_first_valid_callback_delta':0,'peer_starvation_recovery_success_delta':0,'peer_starvation_recovery_failure_delta':0},'acquisition_state_at_end':{'logical_acquisition_strategy':'FILTERED_PRIMARY','recovery_attempts_in_current_5min_window':0,'filtered_probe_window_ms':15000,'filtered_probe_exit_target_ms':14500},'per_peer_at_end':[{'node_id':pid,'run_starvation_recovery_participation_count':0,'run_first_callback_after_recovery_count':0,'run_starvation_recovery_success_count':0,'run_starvation_recovery_failure_count':0,'acquisition':{'run_first_callback_after_recovery_count':0}} for pid in peers],'events':[],'fused_range_observations_at_end':observations(node)}
'''
g = replace_once(g, old, new, "short fixture telemetry")
old = '''x=copy.deepcopy(base); x['validation_run']['validation_counters']['recovery_first_valid_callback_delta']=0; corruptions['counter-mismatch.json']=('RECOVERY_COUNTER_EVENT_MISMATCH',x)
x=copy.deepcopy(base); x['validation_run']['events'][5]['wall_ms']=x['validation_run']['events'][4]['wall_ms']+15001; x['validation_run']['events'][5]['elapsed_ms']=18002; x['validation_run']['events'][5]['elapsed_from_run_start_ms']=18002; corruptions['probe-expired.json']=('FILTERED_PROBE_HARD_LIMIT_EXCEEDED',x)
'''
new = '''x=copy.deepcopy(base); x['validation_run']['validation_counters']['recovery_first_valid_callback_delta']=0; corruptions['counter-mismatch.json']=('RECOVERY_COUNTER_EVENT_MISMATCH',x)
x=copy.deepcopy(base); x['validation_run']['per_peer_at_end'][0]['acquisition']['run_first_callback_after_recovery_count']=0; corruptions['nested-counter-mismatch.json']=('RECOVERY_COUNTER_EVENT_MISMATCH',x)
x=copy.deepcopy(base); x['validation_run']['acquisition_state_at_end']['logical_acquisition_strategy']='FAILED_SAFE'; corruptions['failed-safe-at-end.json']=('FAILED_SAFE_AT_END',x)
x=copy.deepcopy(base); x['validation_run']['events'][5]['wall_ms']=x['validation_run']['events'][4]['wall_ms']+15001; x['validation_run']['events'][5]['elapsed_ms']=18002; x['validation_run']['events'][5]['elapsed_from_run_start_ms']=18002; corruptions['probe-expired.json']=('FILTERED_PROBE_HARD_LIMIT_EXCEEDED',x)
'''
g = replace_once(g, old, new, "new corrupted fixtures")
GEN.write_text(g)

# Align the published operator instructions with the repaired run boundary.
d = DOCS.read_text()
header = "## 4. Directed physical smoke — exactly one LONG + one SHORT per phone"
insert = '''## 4. Directed physical smoke — exactly one LONG + one SHORT per phone

After each completed LONG export, the SHORT must be startable without waiting for the rolling recovery window to expire. If the previous completed run left the controller in `FAILED_SAFE` or `COOLDOWN`, dev-15 normalizes only that filtered terminal state to `FILTERED_PRIMARY` at the new-run boundary. It does **not** erase the frozen 3-attempts/5-minute history or the 30-second cooldown. If the remote peer is genuinely absent, wait until `expected_ble_peer_count: 1` before starting.
'''
if insert not in d:
    if header not in d:
        raise SystemExit("docs header not found")
    d = d.replace(header, insert, 1)
DOCS.write_text(d)
print("DEV15_SESSION_BOUNDARY_FOLLOWUP_APPLIED")
