#!/usr/bin/env python3
import argparse,json,sys
from pathlib import Path
ap=argparse.ArgumentParser(); ap.add_argument('--device',action='append',default=[]); ap.add_argument('--out',default='acceptance_report.json'); ap.add_argument('--md',default=None); a=ap.parse_args()
result={'release':'dev-13','devices':{},'pass':True,'screenshots_required':False}
for spec in a.device:
 name,path=spec.split('=',1); d=json.load(open(path)); r=d.get('validation_run',d); env=r.get('environment') or {}; pf=r.get('preflight_at_start') or {}
 checks={'snapshot_frozen':r.get('snapshot_frozen') is True,'schema_v3':r.get('snapshot_schema_version')==3,'elapsed':r.get('elapsed_ms',0)>=300000,'duration_eligible':r.get('acceptance_duration_eligible') is True,'short_false':r.get('short_diagnostic_run') is False,'preflight':pf.get('ready') is True and pf.get('acquisition_strategy')=='FILTERED_PRIMARY' and pf.get('hardware_filter_count',0)>0,'usable_metric':(r.get('usable_metric_range_uptime_percent') or 0)>=90,'geometry_2d':(r.get('geometry_2d_uptime_percent') or 0)>=90,'peer_expire':r.get('peer_expire_delta')==0,'recovery_budget':r.get('recovery_attempt_delta',99)<=3,'environment':r.get('environment_valid') is True and env.get('valid') is True,'unauthorized_strategy':env.get('unauthorized_strategy_violation_count',0)==0}
 passed=all(checks.values()); result['devices'][name]={'checks':checks,'pass':passed}; result['pass'] &= passed
Path(a.out).write_text(json.dumps(result,indent=2)+'\n')
md=Path(a.md or str(Path(a.out).with_suffix('.md'))); lines=['# dev-13 acceptance report','',f"Overall: **{'PASS' if result['pass'] else 'FAIL'}**",'', '| Device | Result |','|---|---|']
for name,v in result['devices'].items(): lines.append(f"| {name} | {'PASS' if v['pass'] else 'FAIL'} |")
lines += ['', 'Evidence is JSON-based; screenshots are not required.']; md.write_text('\n'.join(lines)+'\n')
print(json.dumps(result,indent=2)); sys.exit(0 if result['pass'] else 1)
