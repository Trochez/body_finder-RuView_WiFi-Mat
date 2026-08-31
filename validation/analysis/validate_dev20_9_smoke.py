#!/usr/bin/env python3
import argparse,json,pathlib,sys,hashlib
BUILD='0.2.0-experimental.20.9'; ALG='deterministic-multinode-rssi-fusion-v8'; PH='5d404d404e08d33cd179aa8657edd93f1e51885f5dfa1268af228465642a8d39'
def load(p): return json.loads(pathlib.Path(p).read_text())
def main():
 ap=argparse.ArgumentParser();ap.add_argument('exports',nargs='+');ap.add_argument('--output',default='dev20.9-smoke-go-no-go.json');a=ap.parse_args();fails=[];docs=[load(p) for p in a.exports]
 if len(docs)!=6:fails.append({'category':'SCENARIO','reason':'EXPECTED_6_EXPORTS','actual':len(docs)})
 scenarios=[d.get('scenario') or d.get('export_metadata',{}).get('scenario') for d in docs]
 if scenarios.count('SMOKE_CAL_EMPTY')!=3 or scenarios.count('HUMAN_MOVING')!=3:fails.append({'category':'SCENARIO','reason':'EXPECTED_3_EMPTY_3_HUMAN','actual':scenarios})
 ids={(d.get('capabilities',{}).get('model'),d.get('node_id') or d.get('local',{}).get('node_id')) for d in docs}
 if len(ids)!=3:fails.append({'category':'AUTHORITY','reason':'EXPECTED_3_DEVICE_NODE_IDENTITIES','actual':len(ids)})
 for i,d in enumerate(docs):
  s=scenarios[i];p=d.get('human_presence_preview') or d.get('validation_run',{}).get('validation_truth',{}).get('authoritative_presence') or {};w=d.get('local',{}).get('wire_transport_v9',{}) or d.get('fabric_diagnostics',{}).get('wire_transport_v9',{})
  checks=[('SNAPSHOT',d.get('build')==BUILD,'BUILD_MISMATCH'),('SCENARIO',s not in (None,'UNSPECIFIED'),'UNSPECIFIED'),('SNAPSHOT',d.get('evidence_export_valid') is True,'EVIDENCE_INVALID'),('AUTHORITY',p.get('authoritative') is True,'NOT_AUTHORITATIVE'),('AUTHORITY',bool(p.get('canonical_digest')),'MISSING_DIGEST'),('ARTIFACT',bool(p.get('canonical_replay_input')),'MISSING_REPLAY'),('AUTHORITY',int(p.get('contributing_nodes',0))>=3 and int(p.get('contributing_links',0))>=6 and int(p.get('physical_baselines',0))>=3,'TOPOLOGY_NOT_3_6_3'),('TRANSPORT',int(w.get('max_datagram_bytes_observed',999999))<=1200,'MTU_EXCEEDED'),('TRANSPORT',int(w.get('wire_oversize_block_count',1))==0,'OVERSIZE_BLOCKED'),('TRANSPORT',int(w.get('wire_send_error_count',1))==0,'SEND_ERROR'),('TRANSPORT',int(w.get('required_frame_oversize_count',1))==0,'REQUIRED_FRAME_OVERSIZE'),('TRANSPORT',int((w.get('tx_frames_by_type') or {}).get('RANGE_FRAME',0))>0,'NO_RANGE_TX'),('TRANSPORT',int((w.get('rx_frames_by_type') or {}).get('RANGE_FRAME',0))>0,'NO_RANGE_RX')]
  expected='NO_HUMAN_EVIDENCE' if s=='SMOKE_CAL_EMPTY' else 'HUMAN_EVIDENCE';checks.append(('DETECTOR',p.get('prediction')==expected,f'EXPECTED_{expected}'))
  for cat,ok,reason in checks:
   if not ok:fails.append({'index':i,'category':cat,'reason':reason})
 for s in ('SMOKE_CAL_EMPTY','HUMAN_MOVING'):
  group=[d for d,sc in zip(docs,scenarios) if sc==s];keys={( (d.get('human_presence_preview') or {}).get('decision_id'),(d.get('human_presence_preview') or {}).get('canonical_digest'),(d.get('human_presence_preview') or {}).get('prediction')) for d in group}
  if len(group)==3 and len(keys)!=1:fails.append({'category':'AUTHORITY','reason':'PEER_DECISION_PARITY_MISMATCH','scenario':s})
 out={'schema':'dev20.9-smoke-verdict-v2','export_count':len(docs),'failures':fails,'failure_count':len(fails),'g10_go':not fails,'g11_go':False,'g12_go':False,'final_go':False,'physical_acceptance':'SMOKE_GO' if not fails else 'SMOKE_NO_GO','dev21_blocked':True,'g11_campaign':'UNBLOCKED_FOR_EXECUTION' if not fails else 'BLOCKED'};pathlib.Path(a.output).write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2));return 0 if not fails else 2
if __name__=='__main__':sys.exit(main())
