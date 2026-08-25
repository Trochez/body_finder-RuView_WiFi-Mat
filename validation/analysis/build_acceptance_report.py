#!/usr/bin/env python3
import json,sys,pathlib
rows=[]; ok=True
for f in sys.argv[1:]:
 p=json.load(open(f)); r=p.get('validation_run',p); passed=r.get('snapshot_frozen') is True and r.get('acceptance_duration_eligible') is True and r.get('environment_valid',r.get('environment',{}).get('valid')) is True and float(r.get('usable_metric_range_uptime_percent',-1))>=90 and float(r.get('geometry_2d_uptime_percent',-1))>=90 and r.get('peer_expire_delta',r.get('validation_counters',{}).get('peer_expire_delta'))==0 and r.get('recovery_attempt_delta',99)<=3
 rows.append({'file':pathlib.Path(f).name,'run_id':r.get('run_id'),'pass':passed,'usable_metric_range_uptime_percent':r.get('usable_metric_range_uptime_percent'),'geometry_2d_uptime_percent':r.get('geometry_2d_uptime_percent'),'peer_expire_delta':r.get('peer_expire_delta'),'recovery_attempt_delta':r.get('recovery_attempt_delta'),'environment_valid':r.get('environment_valid')}); ok &= passed
out={'release':'dev-12','hard_gates_pass':ok,'devices':rows}; print(json.dumps(out,indent=2)); sys.exit(0 if ok else 2)
