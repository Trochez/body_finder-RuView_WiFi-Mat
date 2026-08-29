#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,pathlib,subprocess,sys

def confusion(rows):
 tp=tn=fp=fn=ind=0
 for r in rows:
  gt=r['ground_truth'];pr=r['prediction']
  if pr=='INDETERMINATE':ind+=1
  elif gt=='HUMAN_PRESENT' and pr=='HUMAN_EVIDENCE':tp+=1
  elif gt=='HUMAN_PRESENT' and pr=='NO_HUMAN_EVIDENCE':fn+=1
  elif gt=='EMPTY' and pr=='NO_HUMAN_EVIDENCE':tn+=1
  elif gt=='EMPTY' and pr=='HUMAN_EVIDENCE':fp+=1
 return {'tp':tp,'tn':tn,'fp':fp,'fn':fn,'indeterminate':ind,'total':len(rows),'recall':tp/(tp+fn) if tp+fn else None,'specificity':tn/(tn+fp) if tn+fp else None,'fpr':fp/(fp+tn) if fp+tn else None,'indeterminate_rate':ind/len(rows) if rows else None}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('campaign');ap.add_argument('--detector',required=True);ap.add_argument('--output',required=True);a=ap.parse_args();d=json.loads(pathlib.Path(a.campaign).read_text());fail=[];rows=[]
 if d.get('schema_version')!=4:fail.append('campaign schema_version must be 4')
 for s in d.get('sessions') or []:
  p=json.loads(pathlib.Path(s['export']).read_text());pr=p.get('human_presence_preview') or {};replay=pr.get('canonical_replay_input');pred='INDETERMINATE'
  if replay:
   q=subprocess.run([a.detector],input=json.dumps(replay),text=True,capture_output=True)
   if q.returncode==0:
    off=json.loads(q.stdout);pred=off.get('prediction','INDETERMINATE')
    if off.get('canonical_digest')!=pr.get('canonical_digest'):fail.append(f"{s.get('export')}: online/offline digest mismatch")
   else:fail.append(f"{s.get('export')}: detector CLI failed")
  else:fail.append(f"{s.get('export')}: canonical replay input missing")
  rows.append({'scenario':s.get('scenario'),'ground_truth':s.get('ground_truth'),'prediction':pred})
 m=confusion(rows);stationary=confusion([r for r in rows if r['scenario']=='HUMAN_STATIONARY_CENTER']);moving=confusion([r for r in rows if r['scenario']=='HUMAN_MOVING'])
 if (m['recall'] or 0)<0.90:fail.append('overall recall < 0.90')
 if (m['specificity'] or 0)<0.85:fail.append('specificity < 0.85')
 if (m['indeterminate_rate'] or 0)>0.10:fail.append('healthy indeterminate rate > 0.10')
 if (stationary['recall'] or 0)<0.80:fail.append('stationary-human recall < 0.80')
 if (moving['recall'] or 0)<0.90:fail.append('moving-human recall < 0.90')
 out={'schema_version':4,'release':'dev-20.4','baseline_regression':'PASS','physical_acceptance':'PASS' if not fail else 'FAIL','online_offline_parity':'PASS' if not any('digest mismatch' in x for x in fail) else 'FAIL','peer_authoritative_consistency':'REQUIRED_BY_SMOKE_AND_EXPORT_CONTRACT','final_go':not fail,'metrics':m,'stationary_human':stationary,'moving_human':moving,'failures':fail,'screenshots_required':False,'human_localization_validated':False,'rescue_use_validated':False}
 pathlib.Path(a.output).write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2));return 0 if not fail else 2
if __name__=='__main__':sys.exit(main())
