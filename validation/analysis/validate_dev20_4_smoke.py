#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, pathlib, subprocess, sys
EXPECTED_BUILD='0.2.0-experimental.20.4'
EXPECTED_ALGO='deterministic-multinode-rssi-fusion-v4'
EXPECTED_HASH='9d111630f6109316b65650a5c119dbff2fdc990528d58826641d56b29fd9daa6'

def load(p): return json.loads(pathlib.Path(p).read_text(encoding='utf-8'))
def stable_sha(obj): return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def scenario(path,doc):
    s=str(doc.get('scenario') or (doc.get('export_metadata') or {}).get('scenario') or path).lower()
    if 'human' in s and ('moving' in s or 'mov' in s): return 'HUMAN_MOVING'
    if 'empty' in s or 'smoke_cal' in s or 'calibration' in s: return 'SMOKE_CAL'
    return 'UNKNOWN'
def presence(doc):
    run=doc.get('validation_run') or {}; truth=run.get('validation_truth') or run.get('truth') or {}
    return truth.get('authoritative_presence') or doc.get('human_presence_preview') or {}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('exports',nargs='+');ap.add_argument('--detector',required=True);ap.add_argument('--output',default='smoke-go-no-go.json');a=ap.parse_args();fail=[]
    if len(a.exports)!=6: fail.append(f'exactly 6 exports required, got {len(a.exports)}')
    rows=[]
    for p in a.exports:
      try:d=load(p)
      except Exception as e: fail.append(f'{p}: unreadable JSON: {e}');continue
      pr=presence(d);meta=d.get('export_metadata') or {};pre=(d.get('validation_run') or {}).get('preflight_at_start') or d.get('validation_preflight') or {}
      row={'path':p,'scenario':scenario(p,d),'node_id':d.get('node_id') or meta.get('node_id'),'device_model':meta.get('device_model'),'build':d.get('build'),'presence':pr,'preflight':pre,'environment_valid':bool((d.get('validation_run') or {}).get('environment_valid',True))}
      rows.append(row)
      if row['build']!=EXPECTED_BUILD: fail.append(f'{p}: build mismatch')
      if pr.get('algorithm_version')!=EXPECTED_ALGO or pr.get('parameter_hash')!=EXPECTED_HASH: fail.append(f'{p}: detector version/hash mismatch')
      if not bool(pre.get('ready',pre.get('expected_ble_peers_ready',False))): fail.append(f'{p}: preflight not ready')
      if int(pre.get('expected_ble_peer_count',pre.get('expected_peer_count',0)))<2: fail.append(f'{p}: fewer than 2 expected peers')
      if not row['environment_valid']: fail.append(f'{p}: environment invalid')
    nodes={r['node_id'] for r in rows if r['node_id']}; models={r['device_model'] for r in rows if r['device_model']}
    if len(nodes)!=3: fail.append(f'exactly 3 unique node IDs required, got {len(nodes)}')
    if not {'Pixel 10 Pro','Pixel 7 Pro','Lenovo TB-J606L'}.issubset(models): fail.append(f'target device set mismatch: {sorted(models)}')
    for scen in ('SMOKE_CAL','HUMAN_MOVING'):
      group=[r for r in rows if r['scenario']==scen]
      if len(group)!=3: fail.append(f'{scen}: exactly 3 exports required, got {len(group)}');continue
      ps=[r['presence'] for r in group]
      digests={p.get('canonical_digest') for p in ps if p.get('canonical_digest')}; decisions={p.get('decision_id') for p in ps if p.get('decision_id')}
      if len(digests)!=1 or len(decisions)!=1: fail.append(f'{scen}: peer authoritative decision/digest mismatch')
      for p in ps:
        if p.get('calibration_state')!='READY': fail.append(f'{scen}: calibration not READY')
        if int(p.get('contributing_nodes',0))<3 or int(p.get('contributing_links',0))<6 or int(p.get('physical_baselines',0))<3: fail.append(f'{scen}: online topology is not 3/6/3')
        replay=p.get('canonical_replay_input')
        if not replay: fail.append(f'{scen}: canonical_replay_input missing');continue
        proc=subprocess.run([a.detector],input=json.dumps(replay),text=True,capture_output=True)
        if proc.returncode: fail.append(f'{scen}: detector CLI failed: {proc.stderr.strip()}');continue
        try: off=json.loads(proc.stdout)
        except Exception as e: fail.append(f'{scen}: offline replay invalid JSON: {e}');continue
        if off.get('canonical_digest')!=p.get('canonical_digest') or off.get('prediction')!=p.get('prediction'): fail.append(f'{scen}: exact online/offline parity failed')
      if scen=='HUMAN_MOVING' and any(p.get('prediction')!='HUMAN_EVIDENCE' for p in ps): fail.append('HUMAN_MOVING must be HUMAN_EVIDENCE on all peers')
    base={'schema_version':1,'release':'dev-20.4','build':EXPECTED_BUILD,'algorithm_version':EXPECTED_ALGO,'detector_parameter_hash':EXPECTED_HASH,'export_count':len(rows),'device_count':len(nodes),'failures':fail,'final_go':not fail,'physical_acceptance':'SMOKE_GO' if not fail else 'SMOKE_NO_GO','screenshots_required':False,'human_localization_validated':False,'rescue_use_validated':False}
    base['validator_signature_algorithm']='sha256-canonical-json';base['validator_signature']='sha256:'+stable_sha(base);pathlib.Path(a.output).write_text(json.dumps(base,indent=2)+'\n');print(json.dumps(base,indent=2));return 0 if not fail else 2
if __name__=='__main__':sys.exit(main())
