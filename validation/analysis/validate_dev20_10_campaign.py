#!/usr/bin/env python3
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
 o={'schema_version':13,'release':'dev-20.10','export_count':len(fs),'recall':rec,'specificity':spec,'indeterminate_rate':ir,'moving_recall':mr,'stationary_recall':sr,'failures':fail,'g11_go':not fail,'g12_go':False,'final_go':False,'dev21_blocked':True};pathlib.Path(a.output).write_text(json.dumps(o,indent=2));print(json.dumps(o,indent=2));return 0 if not fail else 2
if __name__=='__main__':sys.exit(main())
