#!/usr/bin/env python3
import argparse, json, pathlib, subprocess, sys
from collections import defaultdict
from datetime import datetime, timezone

BUILD='0.2.0-experimental.20.8'
ALGO='deterministic-multinode-rssi-fusion-v8'
PH='5d404d404e08d33cd179aa8657edd93f1e51885f5dfa1268af228465642a8d39'
SCHEMA='dev20.8-self-contained-json-evidence-v11'
SCENARIOS={
 'EMPTY_CAL','EMPTY_TEST','HUMAN_STATIONARY_CENTER','HUMAN_MOVING',
 'HUMAN_NEAR_LENOVO','HUMAN_NEAR_PIXEL10','HUMAN_NEAR_PIXEL7',
 'HUMAN_OUTSIDE','NON_HUMAN_MOTION'
}
HUMAN={'HUMAN_STATIONARY_CENTER','HUMAN_MOVING','HUMAN_NEAR_LENOVO','HUMAN_NEAR_PIXEL10','HUMAN_NEAR_PIXEL7'}
NEG={'EMPTY_CAL','EMPTY_TEST','HUMAN_OUTSIDE','NON_HUMAN_MOTION'}

def presence(d):
    r=d.get('validation_run') or {}
    return (r.get('validation_truth') or {}).get('authoritative_presence') or d.get('human_presence_preview') or {}

def metadata(d): return d.get('export_metadata') or {}
def scenario(d):
    r=d.get('validation_run') or {}; t=r.get('validation_truth') or {}; m=metadata(d)
    return str(m.get('scenario') or d.get('scenario') or t.get('scenario') or '')

def day_id(d):
    m=metadata(d); r=d.get('validation_run') or {}
    explicit=m.get('campaign_day') or m.get('day_id') or r.get('campaign_day') or d.get('campaign_day')
    if explicit: return str(explicit)
    iso=m.get('generated_at') or d.get('generated_at')
    if isinstance(iso,str) and len(iso)>=10: return iso[:10]
    wall=r.get('started_wall_ms') or r.get('ended_wall_ms')
    if isinstance(wall,(int,float)) and wall>0: return datetime.fromtimestamp(wall/1000,tz=timezone.utc).date().isoformat()
    return ''

def node_id(d):
    m=metadata(d); return str(m.get('node_id') or d.get('node_id') or '')

def calibration(d,p):
    r=d.get('validation_run') or {}; t=r.get('validation_truth') or {}
    return d.get('human_presence_calibration_status') or t.get('human_presence_calibration_status') or {}

def replay(detector,p,path,fails):
    inp=p.get('canonical_replay_input')
    if not isinstance(inp,dict): fails.append(f'{path}: canonical replay missing'); return
    q=subprocess.run([detector],input=json.dumps(inp),text=True,capture_output=True)
    if q.returncode: fails.append(f'{path}: detector CLI failed ({q.returncode})'); return
    try: off=json.loads(q.stdout)
    except Exception: fails.append(f'{path}: detector CLI emitted invalid JSON'); return
    if off.get('canonical_digest')!=p.get('canonical_digest') or off.get('prediction')!=p.get('prediction'): fails.append(f'{path}: Android/CLI canonical parity failed')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('exports',nargs='+'); ap.add_argument('--detector',required=True); ap.add_argument('--output',default='dev20.8-campaign-go-no-go.json')
    a=ap.parse_args(); fails=[]; rows=[]
    if len(a.exports)!=54: fails.append(f'exactly 54 exports required, got {len(a.exports)}')
    for path in a.exports:
        try: d=json.loads(pathlib.Path(path).read_text())
        except Exception as e: fails.append(f'{path}: unreadable JSON: {e}'); continue
        p=presence(d); c=calibration(d,p); sc=scenario(d); day=day_id(d); node=node_id(d); r=d.get('validation_run') or {}; dur=int(r.get('elapsed_ms') or r.get('duration_ms') or 0)
        if sc not in SCENARIOS: fails.append(f'{path}: unknown/missing scenario {sc!r}')
        if not day: fails.append(f'{path}: campaign day/timestamp missing')
        if not node: fails.append(f'{path}: node id missing')
        if dur<330000: fails.append(f'{path}: duration <330s ({dur}ms)')
        if d.get('build')!=BUILD: fails.append(f'{path}: build mismatch')
        if (d.get('evidence_contract') or {}).get('schema')!=SCHEMA: fails.append(f'{path}: evidence schema mismatch')
        if not d.get('evidence_export_valid',False) or not d.get('atomic_snapshot_gate_pass',False): fails.append(f'{path}: frozen evidence invalid')
        if not p.get('authoritative',False): fails.append(f'{path}: decision not authoritative')
        if p.get('algorithm_version')!=ALGO or p.get('parameter_hash')!=PH: fails.append(f'{path}: detector identity mismatch')
        if not p.get('canonical_digest') or d.get('snapshot_consistency_digest')!=p.get('canonical_digest'): fails.append(f'{path}: snapshot/canonical digest mismatch')
        if int(p.get('contributing_nodes',0))<3 or int(p.get('contributing_links',0))<6 or int(p.get('physical_baselines',0))<3: fails.append(f'{path}: topology not 3/6/3')
        if not c.get('distributed_calibration_ready',p.get('distributed_calibration_ready',False)): fails.append(f'{path}: distributed calibration not ready')
        replay(a.detector,p,path,fails)
        rows.append({'path':path,'day':day,'scenario':sc,'node':node,'prediction':p.get('prediction'),'p':p,'c':c})
    days={x['day'] for x in rows if x['day']}; nodes={x['node'] for x in rows if x['node']}
    if len(days)!=2: fails.append(f'exactly 2 independent campaign days required, got {sorted(days)}')
    if len(nodes)!=3: fails.append(f'exactly 3 unique node IDs required, got {sorted(nodes)}')
    groups=defaultdict(list)
    for x in rows: groups[(x['day'],x['scenario'])].append(x)
    for day in days:
        for sc in SCENARIOS:
            g=groups[(day,sc)]
            if len(g)!=3: fails.append(f'{day}/{sc}: exactly 3 device exports required, got {len(g)}'); continue
            if len({x['node'] for x in g})!=3: fails.append(f'{day}/{sc}: duplicate/missing node IDs')
            for field in ('calibration_id','calibration_hash','calibration_generation','coordinator_generation','topology_fingerprint','canonical_digest','decision_id'):
                vals={x['p'].get(field) or x['c'].get(field) for x in g}
                if len(vals)!=1 or None in vals or '' in vals: fails.append(f'{day}/{sc}: authoritative peer parity failed for {field}')
    for day in days:
        if sum(1 for x in rows if x['day']==day)!=27: fails.append(f'{day}: expected 27 exports')
    for node in nodes:
        if sum(1 for x in rows if x['node']==node)!=18: fails.append(f'{node}: expected 18 exports across two days')
    tp=sum(1 for x in rows if x['scenario'] in HUMAN and x['prediction']=='HUMAN_EVIDENCE'); fn=sum(1 for x in rows if x['scenario'] in HUMAN and x['prediction']!='HUMAN_EVIDENCE'); tn=sum(1 for x in rows if x['scenario'] in NEG and x['prediction']=='NO_HUMAN_EVIDENCE'); fp=sum(1 for x in rows if x['scenario'] in NEG and x['prediction']!='NO_HUMAN_EVIDENCE'); ind=sum(1 for x in rows if x['prediction']=='INDETERMINATE')
    recall=tp/max(1,tp+fn); specificity=tn/max(1,tn+fp); ind_rate=ind/max(1,len(rows)); moving=[x for x in rows if x['scenario']=='HUMAN_MOVING']; stationary=[x for x in rows if x['scenario']=='HUMAN_STATIONARY_CENTER']; moving_recall=sum(x['prediction']=='HUMAN_EVIDENCE' for x in moving)/max(1,len(moving)); stationary_recall=sum(x['prediction']=='HUMAN_EVIDENCE' for x in stationary)/max(1,len(stationary))
    if recall<.90: fails.append(f'overall recall <0.90 ({recall:.4f})')
    if specificity<.85: fails.append(f'specificity <0.85 ({specificity:.4f})')
    if ind_rate>.10: fails.append(f'healthy indeterminate rate >0.10 ({ind_rate:.4f})')
    if moving_recall<.90: fails.append(f'moving-human recall <0.90 ({moving_recall:.4f})')
    if stationary_recall<.80: fails.append(f'stationary-human recall <0.80 ({stationary_recall:.4f})')
    per_device={}
    for node in sorted(nodes):
        rr=[x for x in rows if x['node']==node]; h=[x for x in rr if x['scenario'] in HUMAN]; n=[x for x in rr if x['scenario'] in NEG]
        per_device[node]={'human_recall':sum(x['prediction']=='HUMAN_EVIDENCE' for x in h)/max(1,len(h)),'specificity':sum(x['prediction']=='NO_HUMAN_EVIDENCE' for x in n)/max(1,len(n)),'indeterminate_rate':sum(x['prediction']=='INDETERMINATE' for x in rr)/max(1,len(rr))}
    per_scenario={sc:{'count':len([x for x in rows if x['scenario']==sc]),'human_evidence':sum(x['prediction']=='HUMAN_EVIDENCE' for x in rows if x['scenario']==sc),'no_human_evidence':sum(x['prediction']=='NO_HUMAN_EVIDENCE' for x in rows if x['scenario']==sc),'indeterminate':sum(x['prediction']=='INDETERMINATE' for x in rows if x['scenario']==sc)} for sc in sorted(SCENARIOS)}
    out={'schema_version':2,'release':'dev-20.7','build':BUILD,'algorithm_version':ALGO,'detector_parameter_hash':PH,'export_count':len(rows),'days':sorted(days),'nodes':sorted(nodes),'recall':recall,'specificity':specificity,'indeterminate_rate':ind_rate,'moving_recall':moving_recall,'stationary_recall':stationary_recall,'per_device':per_device,'per_scenario':per_scenario,'authoritative_peer_parity_required':True,'android_cli_parity_required':True,'human_localization_validated':False,'rescue_use_validated':False,'failures':fails,'final_go':not fails,'physical_acceptance':'CAMPAIGN_GO' if not fails else 'CAMPAIGN_NO_GO','dev21_blocked':bool(fails)}
    pathlib.Path(a.output).write_text(json.dumps(out,indent=2)+'\n'); print(json.dumps(out,indent=2)); return 0 if not fails else 2
if __name__=='__main__': sys.exit(main())
