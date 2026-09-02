#!/usr/bin/env python3
import argparse,collections,json,pathlib,sys

p=argparse.ArgumentParser(description='Validate exactly six dev-20.14 physical acceptance JSONs.')
p.add_argument('files',nargs='+');p.add_argument('--output');a=p.parse_args()
reasons=[];rows=[];scenario_counts=collections.Counter();authority_tuples=set()
if len(a.files)!=6:reasons.append('EXACTLY_6_ACCEPTANCE_JSONS_REQUIRED')
for f in a.files:
 d=json.loads(pathlib.Path(f).read_text(encoding='utf-8'));r=[]
 if d.get('evidence_class')=='PRE_RUN_DIAGNOSTIC_V1' or d.get('acceptance_eligible') is False:r.append('NOT_ACCEPTANCE_EVIDENCE')
 v=d.get('validation_run') or {};truth=v.get('validation_truth') or d.get('validation_truth') or {};auth=truth.get('authority_status') or {};cal=truth.get('human_presence_calibration_status') or {};sc=truth.get('scenario_contract') or {};start=truth.get('distributed_start') or {};freeze=truth.get('freeze_barrier') or {}
 scenario=str(v.get('scenario') or d.get('scenario') or sc.get('scenario') or '')
 if scenario not in ('SMOKE_CAL_EMPTY','HUMAN_MOVING'):r.append('SCENARIO_INVALID')
 else:scenario_counts[scenario]+=1
 if int(v.get('elapsed_ms') or 0)<330000:r.append('DURATION_LT_330000')
 if auth.get('consensus') is not True or int(auth.get('ack_count') or 0)!=3:r.append('AUTHORITY_NOT_3_OF_3')
 view=auth.get('view') or {};coord=view.get('elected_coordinator');gen=view.get('coordinator_generation');digest=view.get('authority_view_digest')
 if not coord or not gen or not digest:r.append('AUTHORITY_PARITY_FIELDS_MISSING')
 else:authority_tuples.add((str(coord),int(gen),str(digest)))
 if int(cal.get('peer_ack_count') or 0)!=3:r.append('CALIBRATION_NOT_3_OF_3')
 if int(sc.get('ack_count') or 0)!=3:r.append('SCENARIO_NOT_3_OF_3')
 if int(start.get('ready_count') or 0)!=3 or start.get('committed') is not True:r.append('RUNSTART_NOT_3_OF_3')
 if int(freeze.get('ready_count') or 0)!=3 or freeze.get('committed') is not True:r.append('SNAPSHOT_NOT_3_OF_3')
 rows.append({'file':f,'scenario':scenario,'status':'PASS' if not r else 'FAIL','reasons':r});reasons+=r
if scenario_counts.get('SMOKE_CAL_EMPTY')!=3:reasons.append('EXACTLY_3_EMPTY_REQUIRED')
if scenario_counts.get('HUMAN_MOVING')!=3:reasons.append('EXACTLY_3_HUMAN_REQUIRED')
if len(authority_tuples)!=1:reasons.append('CROSS_NODE_AUTHORITY_PARITY_FAILED')
ok=len(a.files)==6 and not reasons
out={'schema':'g10-dev20.14-v1','release':'dev-20.14','status':'GO' if ok else 'NO_GO','g10_go':ok,'scenario_counts':dict(scenario_counts),'authority_parity':len(authority_tuples)==1,'items':rows,'reasons':sorted(set(reasons))}
txt=json.dumps(out,indent=2,sort_keys=True)+'\n'
pathlib.Path(a.output).write_text(txt,encoding='utf-8') if a.output else print(txt,end='')
sys.exit(0 if ok else 2)
