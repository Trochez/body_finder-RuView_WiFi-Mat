#!/usr/bin/env python3
import argparse,json,pathlib,subprocess,sys
BUILD='0.2.0-experimental.20.6'; ALGO='deterministic-multinode-rssi-fusion-v6'; PH='0fdb8a3b9ae003cc6d138c970ecdc0237bc2186b440e5469763e2d6c2e49f2f1'; SCHEMA='dev20.6-self-contained-json-evidence-v9'
SCENARIOS={'EMPTY_CAL','EMPTY_TEST','HUMAN_STATIONARY_CENTER','HUMAN_MOVING','HUMAN_NEAR_LENOVO','HUMAN_NEAR_PIXEL10','HUMAN_NEAR_PIXEL7','HUMAN_OUTSIDE','NON_HUMAN_MOTION'}
HUMAN={'HUMAN_STATIONARY_CENTER','HUMAN_MOVING','HUMAN_NEAR_LENOVO','HUMAN_NEAR_PIXEL10','HUMAN_NEAR_PIXEL7'}; NEG=SCENARIOS-HUMAN

def presence(d):
 r=d.get('validation_run') or {};t=r.get('validation_truth') or r.get('truth') or {};return t.get('authoritative_presence') or d.get('human_presence_preview') or {}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('exports',nargs='+');ap.add_argument('--detector',required=True);ap.add_argument('--output',default='dev20.6-campaign-report.json');a=ap.parse_args();fail=[];rows=[]
 if len(a.exports)!=54:fail.append(f'exactly 54 exports required, got {len(a.exports)}')
 for f in a.exports:
  try:d=json.loads(pathlib.Path(f).read_text(encoding='utf-8'))
  except Exception as e:fail.append(f'{f}: unreadable JSON: {e}');continue
  m=d.get('export_metadata') or {};sc=m.get('scenario') or d.get('scenario');r=d.get('validation_run') or {};p=presence(d);cal=d.get('human_presence_calibration_status') or {}
  if d.get('build')!=BUILD:fail.append(f'{f}: build mismatch')
  if (d.get('evidence_contract') or {}).get('schema')!=SCHEMA:fail.append(f'{f}: schema mismatch')
  if sc not in SCENARIOS:fail.append(f'{f}: invalid scenario {sc}')
  if int(m.get('elapsed_ms') or r.get('elapsed_ms') or 0)<330000:fail.append(f'{f}: duration <330s')
  if p.get('algorithm_version')!=ALGO or p.get('parameter_hash')!=PH:fail.append(f'{f}: detector mismatch')
  if p.get('calibration_state')!='READY' or not cal.get('distributed_calibration_ready'):fail.append(f'{f}: calibration not distributed READY')
  if int(p.get('contributing_nodes',0))<3 or int(p.get('contributing_links',0))<6 or int(p.get('physical_baselines',0))<3:fail.append(f'{f}: topology not 3/6/3')
  if d.get('snapshot_consistency_digest')!=p.get('canonical_digest'):fail.append(f'{f}: snapshot consistency failed')
  replay=p.get('canonical_replay_input')
  if not replay:fail.append(f'{f}: canonical replay missing')
  else:
   q=subprocess.run([a.detector],input=json.dumps(replay),text=True,capture_output=True)
   if q.returncode:fail.append(f'{f}: detector replay failed')
   else:
    try:off=json.loads(q.stdout)
    except Exception:off={};fail.append(f'{f}: replay output invalid JSON')
    if off and (off.get('canonical_digest')!=p.get('canonical_digest') or off.get('prediction')!=p.get('prediction')):fail.append(f'{f}: online/offline parity failed')
  rows.append({'path':f,'scenario':sc,'prediction':p.get('prediction'),'node_id':m.get('node_id') or d.get('node_id'),'calibration_id':p.get('calibration_id'),'calibration_hash':p.get('calibration_hash'),'decision_id':p.get('decision_id'),'canonical_digest':p.get('canonical_digest')})
 # Each scenario is two independent days x three peers. The shared calibration_id is the day/triad grouping key.
 for sc in SCENARIOS:
  g=[x for x in rows if x['scenario']==sc]
  if len(g)!=6:fail.append(f'{sc}: expected 6 exports, got {len(g)}')
  by_cal={}
  for x in g:by_cal.setdefault(x['calibration_id'],[]).append(x)
  if None in by_cal:fail.append(f'{sc}: missing calibration id')
  if len([k for k in by_cal if k is not None])!=2:fail.append(f'{sc}: expected exactly two independent calibration generations/days')
  for cal_id,rg in by_cal.items():
   if cal_id is None:continue
   if len(rg)!=3:fail.append(f'{sc}/{cal_id}: synchronized triad must contain 3 peers, got {len(rg)}');continue
   if len({x['node_id'] for x in rg})!=3:fail.append(f'{sc}/{cal_id}: three unique peer node_ids required')
   if len({x['calibration_hash'] for x in rg})!=1:fail.append(f'{sc}/{cal_id}: calibration hash peer mismatch')
   if len({x['decision_id'] for x in rg})!=1 or len({x['canonical_digest'] for x in rg})!=1:fail.append(f'{sc}/{cal_id}: authoritative decision/digest peer mismatch')
 tp=sum(x['scenario'] in HUMAN and x['prediction']=='HUMAN_EVIDENCE' for x in rows);fn=sum(x['scenario'] in HUMAN and x['prediction']!='HUMAN_EVIDENCE' for x in rows);tn=sum(x['scenario'] in NEG and x['prediction']=='NO_HUMAN_EVIDENCE' for x in rows);fp=sum(x['scenario'] in NEG and x['prediction']=='HUMAN_EVIDENCE' for x in rows)
 recall=tp/max(1,tp+fn);spec=tn/max(1,tn+fp);mov=[x for x in rows if x['scenario']=='HUMAN_MOVING'];stat=[x for x in rows if x['scenario']=='HUMAN_STATIONARY_CENTER'];mr=sum(x['prediction']=='HUMAN_EVIDENCE' for x in mov)/max(1,len(mov));sr=sum(x['prediction']=='HUMAN_EVIDENCE' for x in stat)/max(1,len(stat));ind=sum(x['prediction']=='INDETERMINATE' for x in rows)/max(1,len(rows))
 if recall<.90:fail.append(f'recall {recall:.3f}<.90')
 if spec<.85:fail.append(f'specificity {spec:.3f}<.85')
 if mr<.90:fail.append(f'moving recall {mr:.3f}<.90')
 if sr<.80:fail.append(f'stationary recall {sr:.3f}<.80')
 if ind>.10:fail.append(f'indeterminate {ind:.3f}>.10')
 o={'schema_version':2,'release':'dev-20.6','count':len(rows),'recall':recall,'specificity':spec,'moving_recall':mr,'stationary_recall':sr,'healthy_indeterminate_rate':ind,'failures':fail,'final_go':not fail,'dev21_blocked':bool(fail),'screenshots_required':False,'human_localization_validated':False,'rescue_use_validated':False}
 pathlib.Path(a.output).write_text(json.dumps(o,indent=2)+'\n',encoding='utf-8');print(json.dumps(o,indent=2));return 0 if not fail else 2
if __name__=='__main__':sys.exit(main())
