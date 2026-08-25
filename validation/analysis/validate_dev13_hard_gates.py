#!/usr/bin/env python3
import json,sys
p=sys.argv[1]; d=json.load(open(p)); r=d.get('validation_run',d); env=r.get('environment') or {}; pf=r.get('preflight_at_start') or {}
checks={
 'snapshot_schema_version=3':r.get('snapshot_schema_version')==3,
 'snapshot_frozen':r.get('snapshot_frozen') is True,
 'elapsed_ms>=300000':r.get('elapsed_ms',0)>=300000,
 'acceptance_duration_eligible':r.get('acceptance_duration_eligible') is True,
 'short_diagnostic_run=false':r.get('short_diagnostic_run') is False,
 'preflight_ready':pf.get('ready') is True,
 'preflight_primary':pf.get('acquisition_strategy')=='FILTERED_PRIMARY',
 'preflight_filtered':pf.get('filter_mode')=='MANUFACTURER_FILTERED' and pf.get('hardware_filter_count',0)>0,
 'environment_valid':r.get('environment_valid') is True and env.get('valid') is True,
 'no_unauthorized_strategy':env.get('unauthorized_strategy_violation_count',0)==0,
 'no_false_not_filtered_primary':'NOT_FILTERED_PRIMARY' not in (r.get('environment_violation_types') or []) and 'NOT_FILTERED_PRIMARY' not in (env.get('violation_types') or []),
 'usable_metric>=90':(r.get('usable_metric_range_uptime_percent') or 0)>=90,
 'geometry_2d>=90':(r.get('geometry_2d_uptime_percent') or 0)>=90,
 'peer_expire_delta=0':r.get('peer_expire_delta')==0,
 'recovery_attempt_delta<=3':r.get('recovery_attempt_delta',99)<=3,
 'manual_geometry_override=false':d.get('manual_geometry_override') is False,
 'human_scanning=false':d.get('human_scanning_enabled') is False,
 'human_localization=false':d.get('human_localization_validated') is False,
 'rescue_use=false':d.get('rescue_use_validated') is False,
}
ok=all(checks.values()); print(json.dumps({'file':p,'checks':checks,'pass':ok},indent=2)); sys.exit(0 if ok else 1)
