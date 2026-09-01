#!/usr/bin/env python3
import argparse,json,pathlib,sys
p=argparse.ArgumentParser();p.add_argument('files',nargs='+');p.add_argument('--output');a=p.parse_args();reasons=[];rows=[]
if len(a.files)!=6:reasons.append('EXACTLY_6_ACCEPTANCE_JSONS_REQUIRED')
for f in a.files:
 d=json.loads(pathlib.Path(f).read_text());r=[]
 if d.get('evidence_class')=='PRE_RUN_DIAGNOSTIC_V1':r.append('NOT_ACCEPTANCE_EVIDENCE')
 v=d.get('validation_run') or {};truth=v.get('validation_truth') or d.get('validation_truth') or {};auth=truth.get('authority_status') or {};cal=truth.get('human_presence_calibration_status') or {};sc=truth.get('scenario_contract') or {};start=truth.get('distributed_start') or {};freeze=truth.get('freeze_barrier') or {}
 if int(v.get('elapsed_ms') or 0)<330000:r.append('DURATION_LT_330000')
 if auth.get('consensus') is not True or int(auth.get('ack_count') or 0)!=3:r.append('AUTHORITY_NOT_3_OF_3')
 if int(cal.get('peer_ack_count') or 0)!=3:r.append('CALIBRATION_NOT_3_OF_3')
 if int(sc.get('ack_count') or 0)!=3:r.append('SCENARIO_NOT_3_OF_3')
 if int(start.get('ready_count') or 0)!=3 or start.get('committed') is not True:r.append('RUNSTART_NOT_3_OF_3')
 if int(freeze.get('ready_count') or 0)!=3 or freeze.get('committed') is not True:r.append('SNAPSHOT_NOT_3_OF_3')
 rows.append({'file':f,'status':'PASS' if not r else 'FAIL','reasons':r});reasons+=r
ok=len(a.files)==6 and not reasons;out={'schema':'g10-dev20.13-v1','release':'dev-20.13','status':'GO' if ok else 'NO_GO','g10_go':ok,'items':rows,'reasons':sorted(set(reasons))};txt=json.dumps(out,indent=2)+'\n';pathlib.Path(a.output).write_text(txt) if a.output else print(txt,end='');sys.exit(0 if ok else 2)
