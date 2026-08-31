#!/usr/bin/env python3
import argparse,json,pathlib,sys
HUMAN={'HUMAN_STATIONARY_CENTER','HUMAN_MOVING','HUMAN_NEAR_LENOVO','HUMAN_NEAR_PIXEL10','HUMAN_NEAR_PIXEL7'}
NEG={'EMPTY_CAL','EMPTY_TEST','HUMAN_OUTSIDE','NON_HUMAN_MOTION'}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('exports',nargs='+');ap.add_argument('--output',default='dev20.7-campaign-go-no-go.json');a=ap.parse_args();fails=[];rows=[]
 if len(a.exports)!=54:fails.append(f'exactly 54 exports required, got {len(a.exports)}')
 for p in a.exports:
  d=json.loads(pathlib.Path(p).read_text());r=d.get('validation_run') or {};t=r.get('validation_truth') or {};hp=t.get('authoritative_presence') or d.get('human_presence_preview') or {};sc=str((d.get('export_metadata') or {}).get('scenario') or d.get('scenario') or t.get('scenario') or '');pred=hp.get('prediction');dur=int(r.get('elapsed_ms') or 0);
  if dur<330000:fails.append(f'{p}: duration <330s')
  if not d.get('evidence_export_valid',False):fails.append(f'{p}: evidence invalid')
  rows.append((sc,pred))
 tp=sum(1 for s,p in rows if s in HUMAN and p=='HUMAN_EVIDENCE');fn=sum(1 for s,p in rows if s in HUMAN and p!='HUMAN_EVIDENCE');tn=sum(1 for s,p in rows if s in NEG and p=='NO_HUMAN_EVIDENCE');fp=sum(1 for s,p in rows if s in NEG and p!='NO_HUMAN_EVIDENCE');ind=sum(1 for _,p in rows if p=='INDETERMINATE');rec=tp/max(1,tp+fn);spec=tn/max(1,tn+fp);ir=ind/max(1,len(rows));moving=[p for s,p in rows if s=='HUMAN_MOVING'];stationary=[p for s,p in rows if s=='HUMAN_STATIONARY_CENTER'];mr=sum(p=='HUMAN_EVIDENCE' for p in moving)/max(1,len(moving));sr=sum(p=='HUMAN_EVIDENCE' for p in stationary)/max(1,len(stationary));
 if rec<.90:fails.append('recall <0.90')
 if spec<.85:fails.append('specificity <0.85')
 if ir>.10:fails.append('healthy indeterminate >0.10')
 if mr<.90:fails.append('moving recall <0.90')
 if sr<.80:fails.append('stationary recall <0.80')
 out={'release':'dev-20.7','export_count':len(rows),'recall':rec,'specificity':spec,'indeterminate_rate':ir,'moving_recall':mr,'stationary_recall':sr,'failures':fails,'final_go':not fails,'dev21_blocked':bool(fails)};pathlib.Path(a.output).write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2));return 0 if not fails else 2
if __name__=='__main__':sys.exit(main())
