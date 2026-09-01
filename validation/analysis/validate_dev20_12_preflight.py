#!/usr/bin/env python3
import argparse,json,pathlib,sys
ap=argparse.ArgumentParser();ap.add_argument('json',nargs='+');ap.add_argument('--output',default='dev20.12-preflight.json');a=ap.parse_args();errs=[];docs=[]
if len(a.json)!=3:errs.append('EXACTLY_3_DIAGNOSTICS_REQUIRED')
for p in a.json:
 try:docs.append(json.loads(pathlib.Path(p).read_text(encoding='utf-8')))
 except Exception as e:errs.append(f'{p}:{e}')
for i,d in enumerate(docs):
 wt=d.get('wire_transport_v12') or d.get('wire_transport') or {};cal=d.get('human_presence_calibration_status') or d.get('calibration_status') or {}
 if int(wt.get('critical_control_failure_count') or 0):errs.append(f'{i}:CRITICAL_CONTROL_FAILURE')
 if int(wt.get('required_frame_oversize_count') or 0):errs.append(f'{i}:REQUIRED_OVERSIZE')
 if not(cal.get('distributed_calibration_ready') is True or int(cal.get('peer_ack_count') or cal.get('ack_count') or 0)==3):errs.append(f'{i}:CALIBRATION_NOT_3')
out={'release':'dev-20.12','preflight_go':not errs,'errors':errs};pathlib.Path(a.output).write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2));raise SystemExit(0 if not errs else 2)
