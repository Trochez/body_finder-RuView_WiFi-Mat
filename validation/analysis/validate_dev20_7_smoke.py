#!/usr/bin/env python3
import argparse,json,pathlib,subprocess,sys
BUILD='0.2.0-experimental.20.7'; ALGO='deterministic-multinode-rssi-fusion-v7'; PH='7ff358bc4b1f92211e3a32d31285f5ab591c6fb79585c6b99814c1d0383d945d'; SCHEMA='dev20.7-self-contained-json-evidence-v10'
MODELS={'Pixel 10 Pro','Pixel 7 Pro','Lenovo TB-J606L'}
def load(p): return json.loads(pathlib.Path(p).read_text())
def presence(d): return (d.get('validation_run') or {}).get('validation_truth',{}).get('authoritative_presence') or d.get('human_presence_preview') or {}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('exports',nargs='+');ap.add_argument('--detector',required=True);ap.add_argument('--output',default='dev20.7-smoke-go-no-go.json');a=ap.parse_args();fail=[];rows=[]
 if len(a.exports)!=6: fail.append(f'exactly 6 exports required, got {len(a.exports)}')
 for path in a.exports:
  try:d=load(path)
  except Exception as e:fail.append(f'{path}: unreadable JSON: {e}');continue
  m=d.get('export_metadata') or {};p=presence(d);r=d.get('validation_run') or {};c=d.get('human_presence_calibration_status') or (r.get('validation_truth') or {}).get('human_presence_calibration_status') or {};sc=str(m.get('scenario') or d.get('scenario') or (r.get('validation_truth') or {}).get('scenario') or 'UNSPECIFIED');rows.append((path,d,m,p,c,sc))
  if d.get('build')!=BUILD:fail.append(f'{path}: build mismatch')
  if (d.get('evidence_contract') or {}).get('schema')!=SCHEMA:fail.append(f'{path}: schema mismatch')
  if not d.get('evidence_export_valid',False) or not d.get('atomic_snapshot_gate_pass',False):fail.append(f'{path}: frozen evidence invalid')
  if p.get('algorithm_version')!=ALGO or p.get('parameter_hash')!=PH:fail.append(f'{path}: detector mismatch')
  if not p.get('canonical_digest') or d.get('snapshot_consistency_digest')!=p.get('canonical_digest'):fail.append(f'{path}: snapshot digest mismatch/null')
  if not p.get('canonical_replay_input'):fail.append(f'{path}: canonical replay missing')
  if int(p.get('contributing_nodes',0))<3 or int(p.get('contributing_links',0))<6 or int(p.get('physical_baselines',0))<3:fail.append(f'{path}: topology not 3/6/3')
  if not c.get('distributed_calibration_ready',p.get('distributed_calibration_ready',False)):fail.append(f'{path}: calibration not distributed-ready')
 nodes={m.get('node_id') or d.get('node_id') for _,d,m,_,_,_ in rows}-{None};models={m.get('device_model') for _,_,m,_,_,_ in rows}-{None}
 if len(nodes)!=3:fail.append('three unique node IDs required')
 if not MODELS.issubset(models):fail.append(f'target device set mismatch: {sorted(models)}')
 for sc,want in [('SMOKE_CAL_EMPTY','NO_HUMAN_EVIDENCE'),('HUMAN_MOVING','HUMAN_EVIDENCE')]:
  g=[x for x in rows if x[5]==sc]
  if len(g)!=3:fail.append(f'{sc}: exactly 3 exports required');continue
  for field in ['calibration_id','calibration_hash','calibration_generation','coordinator_generation','topology_fingerprint','canonical_digest','decision_id']:
   vals={x[3].get(field) or x[4].get(field) for x in g}
   if len(vals)!=1 or None in vals:fail.append(f'{sc}: {field} parity failed')
  for path,d,m,p,c,_ in g:
   if p.get('prediction')!=want:fail.append(f'{path}: expected {want}, got {p.get("prediction")}')
   replay=p.get('canonical_replay_input')
   if replay:
    q=subprocess.run([a.detector],input=json.dumps(replay),text=True,capture_output=True)
    if q.returncode:fail.append(f'{path}: detector CLI failed');continue
    try:off=json.loads(q.stdout)
    except:fail.append(f'{path}: detector CLI invalid JSON');continue
    if off.get('canonical_digest')!=p.get('canonical_digest') or off.get('prediction')!=p.get('prediction'):fail.append(f'{path}: Android/CLI parity failed')
 out={'schema_version':4,'release':'dev-20.7','build':BUILD,'algorithm_version':ALGO,'detector_parameter_hash':PH,'export_count':len(rows),'failures':fail,'final_go':not fail,'physical_acceptance':'SMOKE_GO' if not fail else 'SMOKE_NO_GO','dev21_blocked':bool(fail),'screenshots_required':False,'human_localization_validated':False,'rescue_use_validated':False}
 pathlib.Path(a.output).write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2));return 0 if not fail else 2
if __name__=='__main__':sys.exit(main())
