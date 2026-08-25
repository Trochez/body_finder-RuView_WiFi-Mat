#!/usr/bin/env python3
import json,sys
p=sys.argv[1]; d=json.load(open(p)); r=d.get('validation_run',d)
checks={
'snapshot_frozen': r.get('snapshot_frozen') is True,
'elapsed_ms>=300000': r.get('elapsed_ms',0)>=300000,
'acceptance_duration_eligible': r.get('acceptance_duration_eligible') is True,
'usable_metric>=90': (r.get('usable_metric_range_uptime_percent') or 0)>=90,
'geometry_2d>=90': (r.get('geometry_2d_uptime_percent') or 0)>=90,
'peer_expire_delta=0': r.get('peer_expire_delta')==0,
'recovery_attempt_delta<=3': r.get('recovery_attempt_delta',99)<=3,
'environment_valid': r.get('environment_valid') is True,
}
print(json.dumps({'file':p,'checks':checks,'pass':all(checks.values())},indent=2)); sys.exit(0 if all(checks.values()) else 1)
