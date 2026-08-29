#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,pathlib,subprocess,sys
BUILD='0.2.0-experimental.20.5'; ALGO='deterministic-multinode-rssi-fusion-v5'; PH='aaf97ff75573489ebc525a080e96ce09247b405f4c3d88136895c87263793b8e'; SCHEMA='dev20.5-self-contained-json-evidence-v8'
MODELS={'Pixel 10 Pro','Pixel 7 Pro','Lenovo TB-J606L'}
def load(p): return json.loads(pathlib.Path(p).read_text(encoding='utf-8'))
def presence(d):
    r=d.get('validation_run') or {}; t=r.get('validation_truth') or r.get('truth') or {}
    return t.get('authoritative_presence') or d.get('human_presence_preview') or {}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('exports',nargs='+'); ap.add_argument('--detector',required=True); ap.add_argument('--output',default='smoke-go-no-go.json'); a=ap.parse_args()
    failures=[]; rows=[]
    if len(a.exports)!=6: failures.append(f'exactly 6 exports required, got {len(a.exports)}')
    for path in a.exports:
        try: d=load(path)
        except Exception as e: failures.append(f'{path}: unreadable JSON: {e}'); continue
        m=d.get('export_metadata') or {}; p=presence(d); c=d.get('human_presence_calibration_status') or {}; r=d.get('validation_run') or {}; pre=r.get('preflight_at_start') or d.get('validation_preflight') or {}
        sc=str(m.get('scenario') or d.get('scenario') or 'UNSPECIFIED')
        rows.append((path,d,m,p,c,pre,sc))
        if d.get('build')!=BUILD: failures.append(f'{path}: build mismatch')
        if (d.get('evidence_contract') or {}).get('schema')!=SCHEMA: failures.append(f'{path}: evidence schema mismatch')
        if p.get('algorithm_version')!=ALGO or p.get('parameter_hash')!=PH: failures.append(f'{path}: detector mismatch')
        if d.get('snapshot_consistency_digest')!=p.get('canonical_digest'): failures.append(f'{path}: snapshot digest mismatch')
        if int(pre.get('expected_ble_peer_count',pre.get('expected_peer_count',2)))<2: failures.append(f'{path}: fewer than 2 expected peers')
    nodes={m.get('node_id') or d.get('node_id') for _,d,m,_,_,_,_ in rows}-{None}
    models={m.get('device_model') for _,_,m,_,_,_,_ in rows}-{None}
    if len(nodes)!=3: failures.append(f'three unique node IDs required, got {len(nodes)}')
    if not MODELS.issubset(models): failures.append(f'target device set mismatch: {sorted(models)}')
    for sc,want in [('SMOKE_CAL_EMPTY','NO_HUMAN_EVIDENCE'),('HUMAN_MOVING','HUMAN_EVIDENCE')]:
        g=[x for x in rows if x[6]==sc]
        if len(g)!=3: failures.append(f'{sc}: exactly 3 exports required'); continue
        ids={x[3].get('calibration_id') for x in g}; hashes={x[3].get('calibration_hash') for x in g}; digests={x[3].get('canonical_digest') for x in g}; decisions={x[3].get('decision_id') for x in g}
        if len(ids)!=1 or None in ids or len(hashes)!=1 or None in hashes: failures.append(f'{sc}: calibration convergence failed')
        if len(digests)!=1 or None in digests or len(decisions)!=1 or None in decisions: failures.append(f'{sc}: authoritative peer parity failed')
        for path,d,m,p,c,pre,_ in g:
            if p.get('calibration_state')!='READY': failures.append(f'{path}: calibration not READY')
            if not c.get('distributed_calibration_ready'): failures.append(f'{path}: calibration not distributed-ready')
            if int(p.get('contributing_nodes',0))<3 or int(p.get('contributing_links',0))<6 or int(p.get('physical_baselines',0))<3: failures.append(f'{path}: topology not 3/6/3')
            replay=p.get('canonical_replay_input')
            if not replay: failures.append(f'{path}: canonical replay missing'); continue
            q=subprocess.run([a.detector],input=json.dumps(replay),text=True,capture_output=True)
            if q.returncode: failures.append(f'{path}: detector CLI failed'); continue
            try: off=json.loads(q.stdout)
            except Exception: failures.append(f'{path}: detector CLI invalid JSON'); continue
            if off.get('canonical_digest')!=p.get('canonical_digest') or off.get('prediction')!=p.get('prediction'): failures.append(f'{path}: online/offline parity failed')
            if p.get('prediction')!=want: failures.append(f'{path}: expected {want}, got {p.get("prediction")}')
    out={'schema_version':2,'release':'dev-20.5','build':BUILD,'algorithm_version':ALGO,'detector_parameter_hash':PH,'export_count':len(rows),'failures':failures,'final_go':not failures,'physical_acceptance':'SMOKE_GO' if not failures else 'SMOKE_NO_GO','dev21_blocked':bool(failures),'screenshots_required':False,'human_localization_validated':False,'rescue_use_validated':False}
    pathlib.Path(a.output).write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8'); print(json.dumps(out,indent=2)); return 0 if not failures else 2
if __name__=='__main__': sys.exit(main())
