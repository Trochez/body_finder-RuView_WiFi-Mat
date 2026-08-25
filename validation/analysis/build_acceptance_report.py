#!/usr/bin/env python3
import argparse,json,subprocess,sys,tempfile,os
ap=argparse.ArgumentParser(); ap.add_argument('--device',action='append',default=[]); ap.add_argument('--out',default='acceptance_report.json'); a=ap.parse_args(); result={'release':'dev-12','devices':{},'pass':True}
for spec in a.device:
 name,path=spec.split('=',1); d=json.load(open(path)); r=d.get('validation_run',d); checks={'snapshot_frozen':r.get('snapshot_frozen') is True,'elapsed':r.get('elapsed_ms',0)>=300000,'duration_eligible':r.get('acceptance_duration_eligible') is True,'usable_metric':(r.get('usable_metric_range_uptime_percent') or 0)>=90,'geometry_2d':(r.get('geometry_2d_uptime_percent') or 0)>=90,'peer_expire':r.get('peer_expire_delta')==0,'recovery_budget':r.get('recovery_attempt_delta',99)<=3,'environment':r.get('environment_valid') is True}; passed=all(checks.values()); result['devices'][name]={'checks':checks,'pass':passed}; result['pass'] &= passed
open(a.out,'w').write(json.dumps(result,indent=2)+'\n'); print(json.dumps(result,indent=2)); sys.exit(0 if result['pass'] else 1)
