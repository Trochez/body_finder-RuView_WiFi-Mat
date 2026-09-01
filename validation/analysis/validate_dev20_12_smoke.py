#!/usr/bin/env python3
import argparse,json,pathlib,sys,hashlib

def get(d,*path,default=None):
 for p in path:
  if not isinstance(d,dict):return default
  d=d.get(p)
 return default if d is None else d

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--evidence-dir',required=True);ap.add_argument('--detector');ap.add_argument('--output',default='g10-dev20.12.json');a=ap.parse_args();files=sorted(pathlib.Path(a.evidence_dir).glob('*.json'));errors=[]
 if len(files)!=6:errors.append(f'EXACTLY_6_JSON_REQUIRED:{len(files)}')
 docs=[]
 for f in files:
  try:docs.append((f,json.loads(f.read_text(encoding='utf-8'))))
  except Exception as e:errors.append(f'{f.name}:JSON:{e}')
 models=set();nodes=set();groups={'SMOKE_CAL_EMPTY':0,'HUMAN_MOVING':0};tokens=set();calids=set();auth=set()
 for f,d in docs:
  v=d.get('validation_run') or {};t=v.get('validation_truth') or d.get('validation_truth') or {};sc=str(v.get('scenario') or d.get('scenario') or t.get('scenario') or '')
  if sc in groups:groups[sc]+=1
  nodes.add(str(d.get('node_id') or v.get('node_id') or ''));models.add(str(get(d,'device','model',default=d.get('device_model',''))))
  token=v.get('campaign_run_token') or t.get('campaign_run_token');tokens.add(str(token or ''))
  cal=t.get('human_presence_calibration_status') or {};calids.add((str(cal.get('calibration_id') or ''),str(cal.get('calibration_hash') or ''),int(cal.get('calibration_generation') or cal.get('generation') or 0)))
  fb=t.get('freeze_barrier') or {};cand=get(fb,'prepare','candidate',default={}) or {};auth.add(str(cand.get('authority_identity_digest') or ''))
  checks=[(int(v.get('elapsed_ms') or 0)>=330000,'ELAPSED_LT_330000'),(bool(v.get('environment_valid')),'ENVIRONMENT_INVALID'),(int(v.get('peer_expire_delta') or 0)==0,'PEER_EXPIRE'),(float(v.get('usable_metric_range_uptime_percent') or 0)>=90,'USABLE_RANGE_LT_90'),(float(v.get('geometry_2d_uptime_percent') or 0)>=90,'GEOMETRY_LT_90'),(bool(v.get('distributed_start_committed')),'START_NOT_NATIVE_COMMITTED'),(bool(v.get('distributed_freeze_committed')),'FREEZE_NOT_NATIVE_COMMITTED'),(bool(d.get('evidence_export_valid')),'EXPORT_INVALID'),(bool(d.get('atomic_snapshot_gate_pass')),'ATOMIC_INVALID')]
  wt=d.get('wire_transport_v12') or d.get('wire_transport') or get(d,'fabric_diagnostics','wire_transport_v12',default={}) or {};checks += [(int(wt.get('critical_control_failure_count') or 0)==0,'CRITICAL_CONTROL_FAILURE'),(int(wt.get('required_frame_oversize_count') or 0)==0,'REQUIRED_OVERSIZE'),(int(wt.get('max_datagram_bytes_observed') or 0)<=1200,'DATAGRAM_GT_1200')]
  ss=t.get('scenario_contract') or {};sb=t.get('distributed_start') or {};checks += [(int(ss.get('ack_count') or 0)==3,'SCENARIO_ACK_NOT_3'),(bool(sb.get('committed')) and int(sb.get('ready_count') or 0)==3,'START_BARRIER_NOT_3'),(bool(fb.get('committed')) and int(fb.get('ready_count') or 0)==3 and fb.get('ready_parity') is True,'FREEZE_BARRIER_NOT_3')]
  for ok,msg in checks:
   if not ok:errors.append(f'{f.name}:{msg}')
 if groups!={'SMOKE_CAL_EMPTY':3,'HUMAN_MOVING':3}:errors.append(f'SCENARIO_COUNTS:{groups}')
 if len({x for x in nodes if x})!=3:errors.append('UNIQUE_NODE_IDS_NOT_3')
 if len(tokens)!=1 or '' in tokens:errors.append('CAMPAIGN_TOKEN_PARITY')
 if len(calids)!=1 or any(not x for x in next(iter(calids),('', '',0))[:2]):errors.append('CALIBRATION_PARITY')
 if len(auth)!=1 or '' in auth:errors.append('AUTHORITY_IDENTITY_PARITY')
 out={'release':'dev-20.12','schema':'dev20.12-g10-verdict-v1','files':[f.name for f,_ in docs],'scenario_counts':groups,'errors':errors,'g10_go':not errors,'G11':'UNBLOCKED' if not errors else 'BLOCKED','G12':'PENDING','final_go':False,'dev21_blocked':True};pathlib.Path(a.output).write_text(json.dumps(out,indent=2,sort_keys=True)+'\n');print(json.dumps(out,indent=2));return 0 if not errors else 2
if __name__=='__main__':raise SystemExit(main())
