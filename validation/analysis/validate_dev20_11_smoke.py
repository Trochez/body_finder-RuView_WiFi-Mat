#!/usr/bin/env python3
import argparse,json,pathlib,subprocess,sys
BUILD="0.2.0-experimental.20.11";EVIDENCE="dev20.11-self-contained-json-evidence-v14";EXPECT={"SMOKE_CAL_EMPTY":"NO_HUMAN_EVIDENCE","HUMAN_MOVING":"HUMAN_EVIDENCE"}
def path(o,p):
 x=o
 try:
  for k in p.split('.'):x=x[k]
  return x
 except Exception:return None
def main():
 a=argparse.ArgumentParser();a.add_argument('--evidence-dir',required=True);a.add_argument('--output',default='dev20.11-smoke-go-no-go.json');a.add_argument('--detector');q=a.parse_args();fs=sorted(pathlib.Path(q.evidence_dir).glob('*.json'));cats={k:[] for k in ['SCENARIO','ACQUISITION','GEOMETRY','TRANSPORT','ARTIFACT','AUTHORITY','SNAPSHOT','DETECTOR','CONTRACT']};F=lambda c,m:cats[c].append(m);docs=[]
 if len(fs)!=6:F('CONTRACT',f'exactly 6 exports required, got {len(fs)}')
 for f in fs:
  try:docs.append((f,json.loads(f.read_text())))
  except Exception as e:F('CONTRACT',f'{f}: invalid JSON {e}')
 cnt={k:0 for k in EXPECT};models=set();nodes=set();parity={}
 for f,d in docs:
  t=str(f);vr=d.get('validation_run') or {};sc=d.get('scenario');pr=path(vr,'validation_truth.authoritative_presence') or d.get('human_presence_preview') or {};ss=path(vr,'validation_truth.scenario_contract') or {};fb=path(vr,'validation_truth.freeze_barrier') or {};wt=path(d,'fabric_diagnostics.wire_transport_v11') or path(d,'local.wire_transport_v11') or {}
  if d.get('build')!=BUILD or d.get('report_version')!=31 or path(d,'evidence_contract.schema')!=EVIDENCE or vr.get('snapshot_schema_version')!=14:F('CONTRACT',t+': release/schema identity')
  if sc not in EXPECT or sc!=path(d,'export_metadata.scenario') or sc!=vr.get('scenario'):F('SCENARIO',t+': internal scenario mismatch')
  else:cnt[sc]+=1
  if not ss.get('ready') or int(ss.get('ack_count') or 0)!=3 or (ss.get('command') or {}).get('scenario')!=sc:F('SCENARIO',t+': ScenarioCommand ACK 3/3')
  if not fb.get('committed') or int(fb.get('ready_count') or 0)!=3 or fb.get('ready_parity') is not True:F('SNAPSHOT',t+': freeze 3/3 parity')
  if int(vr.get('elapsed_ms') or 0)<330000:F('CONTRACT',t+': duration')
  if vr.get('environment_valid') is not True or int(vr.get('peer_expire_delta') if vr.get('peer_expire_delta') is not None else -1)!=0:F('ACQUISITION',t+': environment/peer expiry')
  if float(vr.get('usable_metric_range_uptime_percent') or 0)<90:F('ACQUISITION',t+': usable range')
  if float(vr.get('geometry_2d_uptime_percent') or 0)<90:F('GEOMETRY',t+': geometry')
  if vr.get('evidence_export_valid') is not True or vr.get('atomic_snapshot_gate_pass') is not True:F('SNAPSHOT',t+': atomic evidence')
  if not pr.get('authoritative') or not pr.get('canonical_digest') or not pr.get('decision_id') or not isinstance(pr.get('canonical_replay_input'),dict):F('AUTHORITY',t+': decision/replay')
  if int(pr.get('contributing_nodes') or 0)<3 or int(pr.get('contributing_links') or 0)<6 or int(pr.get('physical_baselines') or 0)<3:F('AUTHORITY',t+': 3/6/3')
  if sc in EXPECT and pr.get('prediction')!=EXPECT[sc]:F('DETECTOR',t+': prediction')
  by=wt.get('max_datagram_bytes_by_type') or {};ck=wt.get('max_control_bytes_by_key') or {}
  if wt.get('schema')!='WireTransportTelemetryV11' or int(wt.get('max_datagram_bytes_observed') or 0)>1200 or int(wt.get('required_frame_oversize_count') or 0)!=0 or int(wt.get('wire_oversize_block_count') or 0)!=0 or int(by.get('CONTROL_FRAME') or 0)>900 or int(by.get('RANGE_FRAME') or 0)>1200 or any(int(x or 0)>900 for x in ck.values()):F('TRANSPORT',t+': MTU')
  if int(wt.get('artifact_reassembly_pending') or 0)>4 or int(wt.get('artifact_nack_tx') or 0)>1000:F('ARTIFACT',t+': bounded artifact budget')
  models.add(str(path(d,'export_metadata.device_model') or ''));nodes.add(str(path(d,'export_metadata.node_id') or d.get('node_id') or ''));cal=path(vr,'validation_truth.human_presence_calibration_status') or {};parity.setdefault(sc,[]).append((cal.get('calibration_id'),cal.get('calibration_hash'),cal.get('generation'),cal.get('topology_fingerprint'),pr.get('decision_id'),pr.get('canonical_digest'),pr.get('prediction')))
  if q.detector and isinstance(pr.get('canonical_replay_input'),dict):
   cp=subprocess.run([q.detector],input=json.dumps(pr['canonical_replay_input']),text=True,capture_output=True);r={}
   try:r=json.loads(cp.stdout) if cp.returncode==0 else {}
   except:pass
   if cp.returncode or r.get('canonical_digest')!=pr.get('canonical_digest') or (r.get('core') or {}).get('prediction')!=pr.get('prediction'):F('DETECTOR',t+': Android/CLI parity')
 if len({x for x in models if x})!=3:F('CONTRACT','3 unique models required')
 if len({x for x in nodes if x})!=3:F('CONTRACT','3 unique nodes required')
 if cnt!={'SMOKE_CAL_EMPTY':3,'HUMAN_MOVING':3}:F('SCENARIO',f'exactly 3 EMPTY + 3 HUMAN: {cnt}')
 for sc,rows in parity.items():
  if sc in EXPECT and rows and len(set(rows))!=1:F('AUTHORITY',f'{sc}: peer parity')
 fail=[m for v in cats.values() for m in v];o={'schema_version':14,'release':'dev-20.11','failure_categories':cats,'failures':fail,'g10_go':not fail,'g11_go':False,'g12_go':False,'final_go':False,'dev21_blocked':True,'screenshots_required':False};pathlib.Path(q.output).write_text(json.dumps(o,indent=2)+'\n');print(json.dumps(o,indent=2));return 0 if not fail else 2
if __name__=='__main__':sys.exit(main())
