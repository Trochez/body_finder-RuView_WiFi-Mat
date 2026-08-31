#!/usr/bin/env python3
from pathlib import Path
import json
R=Path(__file__).resolve().parents[1]
def wr(x,s):p=R/x;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s)
def jw(x,o):wr(x,json.dumps(o,indent=2,sort_keys=True)+'\n')
B='0.2.0-experimental.20.10';E='dev20.10-self-contained-json-evidence-v13';P='f5795d40fbfb1de728b8576e214b249ada67f70d7962e1bf7794eb9c7d251f17';A='deterministic-multinode-rssi-fusion-v9'
smoke='''#!/usr/bin/env python3
import argparse,json,pathlib,subprocess,sys
BUILD="0.2.0-experimental.20.10"; EVIDENCE="dev20.10-self-contained-json-evidence-v13"; REPORT=30; SNAPSHOT=13
EXPECT={"SMOKE_CAL_EMPTY":"NO_HUMAN_EVIDENCE","HUMAN_MOVING":"HUMAN_EVIDENCE"}
def path(o,p):
 x=o
 try:
  for k in p.split('.'):x=x[k]
  return x
 except Exception:return None
def main():
 a=argparse.ArgumentParser();a.add_argument('--evidence-dir',required=True);a.add_argument('--output',default='dev20.10-smoke-go-no-go.json');a.add_argument('--detector');q=a.parse_args();fs=sorted(pathlib.Path(q.evidence_dir).glob('*.json'));cats={k:[] for k in ['SCENARIO','ACQUISITION','GEOMETRY','TRANSPORT','ARTIFACT','CALIBRATION','AUTHORITY','SNAPSHOT','DETECTOR','CONTRACT']};F=lambda c,m:cats[c].append(m);docs=[]
 if len(fs)!=6:F('CONTRACT',f'exactly 6 exports required, got {len(fs)}')
 for f in fs:
  try:docs.append((f,json.loads(f.read_text())))
  except Exception as e:F('CONTRACT',f'{f}: invalid JSON {e}')
 models=set();nodes=set();cnt={k:0 for k in EXPECT};parity={}
 for f,d in docs:
  t=str(f);vr=d.get('validation_run') or {};sc=d.get('scenario');pr=path(vr,'validation_truth.authoritative_presence') or d.get('human_presence_preview') or {};wt=path(d,'fabric_diagnostics.wire_transport_v10') or path(d,'local.wire_transport_v10')
  if d.get('build')!=BUILD or d.get('report_version')!=REPORT or path(d,'evidence_contract.schema')!=EVIDENCE or vr.get('snapshot_schema_version')!=SNAPSHOT:F('CONTRACT',t+': release/schema identity')
  if sc not in EXPECT or sc!=path(d,'export_metadata.scenario') or sc!=vr.get('scenario'):F('SCENARIO',t+': internal scenario mismatch')
  else:cnt[sc]+=1
  if not vr.get('scenario_consistency_digest'):F('SCENARIO',t+': missing scenario digest')
  models.add(str(path(d,'export_metadata.device_model') or ''));nodes.add(str(path(d,'export_metadata.node_id') or d.get('node_id') or ''))
  if int(vr.get('elapsed_ms') or 0)<330000:F('CONTRACT',t+': duration')
  if vr.get('environment_valid') is not True:F('ACQUISITION',t+': environment')
  if int(vr.get('peer_expire_delta') if vr.get('peer_expire_delta') is not None else -1)!=0:F('ACQUISITION',t+': peer expiry')
  if float(vr.get('usable_metric_range_uptime_percent') or 0)<90:F('ACQUISITION',t+': usable range uptime')
  if float(vr.get('geometry_2d_uptime_percent') or 0)<90:F('GEOMETRY',t+': geometry uptime')
  if int(path(vr,'acquisition_state_at_end.recovery_attempts_max_in_any_rolling_5min_window') or 0)>3:F('ACQUISITION',t+': recovery budget')
  if vr.get('evidence_export_valid') is not True or vr.get('atomic_snapshot_gate_pass') is not True:F('SNAPSHOT',t+': atomic snapshot')
  if pr.get('authoritative') is not True or not pr.get('canonical_digest') or not pr.get('decision_id') or not isinstance(pr.get('canonical_replay_input'),dict):F('AUTHORITY',t+': authoritative digest/replay')
  if int(pr.get('contributing_nodes') or 0)<3 or int(pr.get('contributing_links') or 0)<6 or int(pr.get('physical_baselines') or 0)<3:F('AUTHORITY',t+': topology 3/6/3')
  if sc in EXPECT and pr.get('prediction')!=EXPECT[sc]:F('DETECTOR',f'{t}: expected {EXPECT[sc]}, got {pr.get("prediction")}')
  if not isinstance(wt,dict):F('TRANSPORT',t+': wire_transport_v10 missing')
  else:
   by=wt.get('max_datagram_bytes_by_type') or {}
   if int(wt.get('max_datagram_bytes_observed') or 0)>1200 or int(wt.get('required_frame_oversize_count') or 0)!=0 or int(wt.get('wire_oversize_block_count') or 0)!=0 or int(by.get('CONTROL_FRAME') or 0)>1200 or int(by.get('RANGE_FRAME') or 0)>1200:F('TRANSPORT',t+': MTU')
   if int((wt.get('tx_frames_by_type') or {}).get('RANGE_FRAME',0))<=0 or int((wt.get('rx_frames_by_type') or {}).get('RANGE_FRAME',0))<=0:F('TRANSPORT',t+': RANGE_FRAME tx/rx')
   if wt.get('artifact_transfer_health') not in (None,'HEALTHY'):F('ARTIFACT',t+': artifact transfer health')
  cal=path(vr,'validation_truth.human_presence_calibration_status') or d.get('human_presence_calibration_status') or {};parity.setdefault(sc,[]).append((cal.get('calibration_id'),cal.get('calibration_hash'),cal.get('generation'),cal.get('topology_fingerprint'),pr.get('decision_id'),pr.get('canonical_digest'),pr.get('prediction')))
  if q.detector and isinstance(pr.get('canonical_replay_input'),dict):
   cp=subprocess.run([q.detector],input=json.dumps(pr['canonical_replay_input']),text=True,capture_output=True)
   try:r=json.loads(cp.stdout) if cp.returncode==0 else {}
   except Exception:r={}
   if cp.returncode or r.get('canonical_digest')!=pr.get('canonical_digest') or (r.get('core') or {}).get('prediction')!=pr.get('prediction'):F('DETECTOR',t+': Android/CLI parity')
 if len({x for x in models if x})!=3:F('CONTRACT',f'3 models required: {models}')
 if len({x for x in nodes if x})!=3:F('CONTRACT',f'3 nodes required: {nodes}')
 if cnt!={'SMOKE_CAL_EMPTY':3,'HUMAN_MOVING':3}:F('SCENARIO',f'exactly 3 EMPTY + 3 HUMAN: {cnt}')
 for sc,rows in parity.items():
  if rows and len(set(rows))!=1:F('AUTHORITY',f'{sc}: peer calibration/decision parity')
 fail=[m for v in cats.values() for m in v];o={'schema_version':13,'release':'dev-20.10','build':BUILD,'export_count':len(docs),'failure_categories':cats,'failures':fail,'g10_go':not fail,'g11_go':False,'g12_go':False,'final_go':False,'dev21_blocked':True,'screenshots_required':False};pathlib.Path(q.output).write_text(json.dumps(o,indent=2)+'\n');print(json.dumps(o,indent=2));return 0 if not fail else 2
if __name__=='__main__':sys.exit(main())
'''
wr('validation/analysis/validate_dev20_10_smoke.py',smoke)
campaign='''#!/usr/bin/env python3
import argparse,json,pathlib,sys
H={'HUMAN_STATIONARY_CENTER','HUMAN_MOVING','HUMAN_NEAR_LENOVO','HUMAN_NEAR_PIXEL10','HUMAN_NEAR_PIXEL7'};N={'EMPTY_CAL','EMPTY_TEST','HUMAN_OUTSIDE','NON_HUMAN_MOTION'}
def main():
 p=argparse.ArgumentParser();p.add_argument('--evidence-dir',required=True);p.add_argument('--output',default='dev20.10-campaign-go-no-go.json');a=p.parse_args();fs=sorted(pathlib.Path(a.evidence_dir).glob('*.json'));fail=[];tp=tn=fp=fn=ind=0;groups={};days=set()
 if len(fs)!=54:fail.append(f'exactly 54 JSON required, got {len(fs)}')
 for f in fs:
  try:d=json.loads(f.read_text())
  except Exception as e:fail.append(f'{f}: {e}');continue
  v=d.get('validation_run') or {};sc=d.get('scenario');day=d.get('campaign_day') or (d.get('export_metadata') or {}).get('campaign_day');days.add(str(day));pr=((v.get('validation_truth') or {}).get('authoritative_presence') or d.get('human_presence_preview') or {});pred=pr.get('prediction');groups.setdefault((str(day),sc),[]).append((pr.get('decision_id'),pr.get('canonical_digest'),pred,d.get('node_id')))
  if d.get('build')!='0.2.0-experimental.20.10' or (d.get('evidence_contract') or {}).get('schema')!='dev20.10-self-contained-json-evidence-v13' or v.get('snapshot_schema_version')!=13:fail.append(f'{f}: contract')
  if int(v.get('elapsed_ms') or 0)<330000 or not v.get('environment_valid') or int(v.get('peer_expire_delta') if v.get('peer_expire_delta') is not None else -1)!=0 or float(v.get('usable_metric_range_uptime_percent') or 0)<90 or float(v.get('geometry_2d_uptime_percent') or 0)<90:fail.append(f'{f}: infrastructure')
  if pred=='INDETERMINATE':ind+=1
  elif sc in H:
   if pred=='HUMAN_EVIDENCE':tp+=1
   else:fn+=1
  elif sc in N:
   if pred=='NO_HUMAN_EVIDENCE':tn+=1
   else:fp+=1
 if len(days)!=2:fail.append(f'exactly 2 days required: {days}')
 if len(groups)!=18:fail.append(f'exactly 18 day/scenario groups required: {len(groups)}')
 for k,r in groups.items():
  if len(r)!=3 or len({x[:3] for x in r})!=1:fail.append(f'{k}: peer parity')
 rec=tp/max(1,tp+fn);spec=tn/max(1,tn+fp);ir=ind/max(1,tp+tn+fp+fn+ind);mov=[r for (d,s),rs in groups.items() if s=='HUMAN_MOVING' for r in rs];sta=[r for (d,s),rs in groups.items() if s=='HUMAN_STATIONARY_CENTER' for r in rs];mr=sum(x[2]=='HUMAN_EVIDENCE' for x in mov)/max(1,len(mov));sr=sum(x[2]=='HUMAN_EVIDENCE' for x in sta)/max(1,len(sta))
 if rec<.9:fail.append('recall<.90')
 if spec<.85:fail.append('specificity<.85')
 if ir>.1:fail.append('indeterminate>.10')
 if mr<.9:fail.append('moving recall<.90')
 if sr<.8:fail.append('stationary recall<.80')
 o={'schema_version':13,'release':'dev-20.10','export_count':len(fs),'recall':rec,'specificity':spec,'indeterminate_rate':ir,'moving_recall':mr,'stationary_recall':sr,'failures':fail,'g11_go':not fail,'g12_go':False,'final_go':False,'dev21_blocked':True};pathlib.Path(a.output).write_text(json.dumps(o,indent=2)+'\n');print(json.dumps(o,indent=2));return 0 if not fail else 2
if __name__=='__main__':sys.exit(main())
'''
wr('validation/analysis/validate_dev20_10_campaign.py',campaign)
# schemas
jw('validation/schemas/dev20.10-evidence-schema-v13.json',{'$schema':'https://json-schema.org/draft/2020-12/schema','type':'object','required':['report_version','build','protocol_version','evidence_contract','scenario','validation_run'],'properties':{'report_version':{'const':30},'build':{'const':B},'protocol_version':{'const':2},'json_self_contained':{'const':True},'screenshots_required':{'const':False},'evidence_contract':{'type':'object','properties':{'schema':{'const':E}},'required':['schema']},'validation_run':{'type':'object','properties':{'snapshot_schema_version':{'const':13},'scenario_generation':{'type':'integer','minimum':1},'scenario_consistency_digest':{'type':'string'}},'required':['snapshot_schema_version','scenario','scenario_generation','scenario_consistency_digest']}},'additionalProperties':True})
jw('validation/schemas/dev20.10-campaign-schema.json',{'$schema':'https://json-schema.org/draft/2020-12/schema','type':'object','properties':{'release':{'const':'dev-20.10'},'export_count':{'const':54}},'additionalProperties':True})
jw('validation/schemas/wire-envelope-v10-schema.json',{'$schema':'https://json-schema.org/draft/2020-12/schema','title':'WireEnvelopeV10','type':'object','properties':{'schema':{'const':'WireEnvelopeV10'}},'required':['schema','message_type','session_id','node_id','seq'],'additionalProperties':True})
jw('validation/schemas/range-frame-v9-schema.json',{'$schema':'https://json-schema.org/draft/2020-12/schema','title':'RangeFrameV9','type':'object','additionalProperties':True})
jw('validation/schemas/control-plane-v10-schema.json',{'$schema':'https://json-schema.org/draft/2020-12/schema','title':'ControlPlaneV10','type':'object','additionalProperties':True})
jw('validation/schemas/geometry-publication-v10-schema.json',{'$schema':'https://json-schema.org/draft/2020-12/schema','title':'GeometryPublicationV10','type':'object','required':['frame_id','revision','positions'],'additionalProperties':True})
jw('validation/schemas/artifact-manifest-v2-schema.json',{'$schema':'https://json-schema.org/draft/2020-12/schema','title':'ArtifactManifestV2','type':'object','required':['artifact_id','artifact_type','artifact_sha256','chunk_count'],'additionalProperties':True})
jw('validation/detector-parameter-manifest-v9.json',{'algorithm_version':A,'parameter_hash':P,'global_thresholds':{'human':.50,'no_human':.20,'disturbed':.32},'threshold_only_change':False,'v9_feature_rule':{'coherent_low_amplitude_requires_transition_physical_baselines':2}})
print('dev20.10 validation assets generated')
