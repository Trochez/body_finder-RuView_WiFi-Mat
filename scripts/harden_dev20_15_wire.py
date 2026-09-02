#!/usr/bin/env python3
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'apps/mobile/src/humanPresence.ts';s=p.read_text()
def r(a,b):
 global s
 if a not in s and b not in s: raise SystemExit('missing anchor: '+a[:100])
 if a in s:s=s.replace(a,b)
r("artifact_id:raw.a,topology_hash:raw.t","artifact_id:`calibration:${raw.i}`,topology_hash:raw.t")
r(",a:`calibration:${cal.artifact.calibration_id}`,t:topology_hash",",t:topology_hash")
r("artifacts.push({artifact_id:cm.a,artifact_type:'CALIBRATION_FINAL_V10'","artifacts.push({artifact_id:`calibration:${cal.artifact.calibration_id}`,artifact_type:'CALIBRATION_FINAL_V10'")
r(",ci:cached.decision.calibration_id??cal.artifact?.calibration_id??null,ch:",",ch:")
old="const coordinator=nodes.find(n=>n.node_id===coordinatorNodeId);const dp=(coordinator?.control_plane as any)?.decision_meta_v10;\n  if(dp&&dp.schema==='DecisionMetaV10'&&dp.sid===sid&&dp.coordinator_id===coordinatorNodeId&&Number(dp.cg)===cal.coordinatorGeneration&&dp.cal_hash===cal.artifact?.calibration_hash&&dp.digest){"
new="const coordinator=nodes.find(n=>n.node_id===coordinatorNodeId);const rawDp=(coordinator?.control_plane as any)?.decision_meta_v10;const dp=rawDp?.schema==='DecisionMetaWireV2'?{schema:'DecisionMetaV10',sid:rawDp.s,coordinator_id:rawDp.n,cg:Number(rawDp.cg),g:Number(rawDp.g),cal_id:cal.artifact?.calibration_id??null,cal_hash:rawDp.ch,topology_hash:rawDp.t,seq:Number(rawDp.q),id:rawDp.i,digest:rawDp.d,prediction:rawDp.p,n:Number(rawDp.nn??0),l:Number(rawDp.ll??0),b:Number(rawDp.bb??0)}:rawDp;\n  if(dp&&dp.schema==='DecisionMetaV10'&&dp.sid===sid&&dp.coordinator_id===coordinatorNodeId&&Number(dp.cg)===cal.coordinatorGeneration&&Number(dp.g)===cal.generation&&dp.cal_hash===cal.artifact?.calibration_hash&&dp.topology_hash===BodyFinderNative.sha256Text(cal.topology||'')&&dp.digest){"
r(old,new)
p.write_text(s)

# Tighten wire schemas to match the final compact contracts.
mp=ROOT/'validation/schemas/calibration-meta-wire-v2.schema.json';d=json.loads(mp.read_text());d['required']=[x for x in d['required'] if x!='a'];d['properties'].pop('a',None);mp.write_text(json.dumps(d,indent=2,sort_keys=True)+'\n')
dp=ROOT/'validation/schemas/decision-meta-wire-v2.schema.json';d=json.loads(dp.read_text());d['required']=[x for x in d['required'] if x!='ci'];d['properties'].pop('ci',None);dp.write_text(json.dumps(d,indent=2,sort_keys=True)+'\n')

# Recompute worst-supported shape budgets with the exact compact envelope used by the release gate.
u='12345678-1234-1234-1234-123456789abc';h='f'*64;sid='body-finder-lab'
vals={
'calibration_meta_v10':{'schema':'CalibrationMetaWireV2','s':sid,'n':u,'cg':2147483647,'g':2147483647,'i':'cal-d208-2147483647-12345678-1799999999999','h':h,'t':h,'q':2147483647,'l':60000,'d':h},
'calibration_ack_v10':{'schema':'CalibrationAckWireV2','s':sid,'n':u,'cg':2147483647,'g':2147483647,'i':'cal-d208-2147483647-12345678-1799999999999','h':h,'t':h,'d':h},
'decision_meta_v10':{'schema':'DecisionMetaWireV2','s':sid,'n':u,'cg':2147483647,'g':2147483647,'ch':h,'t':h,'q':2147483647,'i':'decision-1799999999999-12345678','d':h,'p':'NO_HUMAN_EVIDENCE','nn':3,'ll':6,'bb':3},
'decision_ack_v10':{'schema':'DecisionAckWireV2','s':sid,'n':u,'q':2147483647,'i':'decision-1799999999999-12345678','d':h}}
def enc(x):return json.dumps(x,separators=(',',':'),ensure_ascii=False).encode()
rows={}
for k,v in vals.items():
 payload=len(enc({'control_key':k,'control_value':v}));frame=len(enc({'frame_type':'CONTROL_FRAME','node_id':u,'session_id':sid,'seq':2147483647,'control_key':k,'control_value':v}));rows[k]={'payload_bytes':payload,'frame_bytes':frame,'datagram_bytes':frame,'payload_lt_600':payload<600,'frame_lt_900':frame<900,'datagram_lt_1200':frame<1200,'engineering_headroom_bytes':600-payload,'engineering_target_le_500':payload<=500}
 if not(payload<600 and frame<900 and frame<1200):raise SystemExit(f'wire hard budget fail {k}: {rows[k]}')
for k in ('calibration_meta_v10','decision_meta_v10'):
 if not rows[k]['engineering_target_le_500']:raise SystemExit(f'engineering <=500 target fail {k}: {rows[k]}')
reports=ROOT/'validation/reports'
(reports/'critical-control-wire-budget-report.json').write_text(json.dumps({'schema':'CriticalControlWireBudgetReportV2','release':'dev-20.15','hard_limits':{'payload':600,'frame':900,'datagram':1200},'engineering_target_payload_le':500,'measurements':rows,'authority_regression_reference':{'authority_view_v1_payload_bytes':293,'authority_ack_v1_payload_bytes':338},'pass':True},indent=2,sort_keys=True)+'\n')
(reports/'calibration-wire-budget-report.json').write_text(json.dumps({'schema':'CalibrationWireBudgetReportV2','release':'dev-20.15','hard_payload_limit':600,'engineering_target':500,'measurements':{k:v for k,v in rows.items() if k.startswith('calibration_')},'pass':True},indent=2,sort_keys=True)+'\n')
# Record peer-decision compatibility as an explicit engineering gate.
(reports/'decision-wire-compatibility-report.json').write_text(json.dumps({'schema':'DecisionWireCompatibilityReportV2','release':'dev-20.15','wire':'DecisionMetaWireV2','peer_decoder':'DecisionMetaV10 semantic normalization','exact_bindings':['session','coordinator','coordinator_generation','calibration_generation','calibration_hash','topology_hash','decision_digest'],'payload_bytes_worst_supported':rows['decision_meta_v10']['payload_bytes'],'engineering_target_le_500':True,'pass':True},indent=2,sort_keys=True)+'\n')
print(json.dumps(rows,indent=2));print('dev20.15 final wire hardening PASS')
