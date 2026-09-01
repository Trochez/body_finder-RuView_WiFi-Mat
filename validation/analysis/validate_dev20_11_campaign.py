#!/usr/bin/env python3
import argparse,json,pathlib,sys
p=argparse.ArgumentParser();p.add_argument('--evidence-dir',required=True);p.add_argument('--output',default='dev20.11-campaign-go-no-go.json');a=p.parse_args();fs=sorted(pathlib.Path(a.evidence_dir).glob('*.json'));fail=[]
if len(fs)!=54:fail.append(f'exactly 54 exports required, got {len(fs)}')
rows=[]
for f in fs:
 try:
  d=json.loads(f.read_text());vr=d.get('validation_run') or {};pr=(vr.get('validation_truth') or {}).get('authoritative_presence') or d.get('human_presence_preview') or {};gt=str(d.get('ground_truth') or (d.get('export_metadata') or {}).get('ground_truth') or d.get('scenario') or '');pred=str(pr.get('prediction') or 'INDETERMINATE');rows.append((gt,pred));
  if vr.get('evidence_export_valid') is not True or vr.get('atomic_snapshot_gate_pass') is not True or float(vr.get('geometry_2d_uptime_percent') or 0)<90 or float(vr.get('usable_metric_range_uptime_percent') or 0)<90:fail.append(str(f)+': infrastructure gate')
 except Exception as e:fail.append(str(f)+': '+str(e))
h=[r for r in rows if 'HUMAN' in r[0] and 'EMPTY' not in r[0]];e=[r for r in rows if 'EMPTY' in r[0]];rec=sum(p=='HUMAN_EVIDENCE' for _,p in h)/max(1,len(h));spec=sum(p=='NO_HUMAN_EVIDENCE' for _,p in e)/max(1,len(e));ind=sum(p=='INDETERMINATE' for _,p in rows)/max(1,len(rows))
if rec<.90:fail.append(f'recall {rec:.3f}<.90')
if spec<.85:fail.append(f'specificity {spec:.3f}<.85')
if ind>.10:fail.append(f'indeterminate {ind:.3f}>.10')
o={'schema_version':14,'release':'dev-20.11','recall':rec,'specificity':spec,'indeterminate_rate':ind,'failures':fail,'g11_go':not fail,'g12_go':False,'final_go':False,'dev21_blocked':True};pathlib.Path(a.output).write_text(json.dumps(o,indent=2)+'\n');print(json.dumps(o,indent=2));sys.exit(0 if not fail else 2)
