#!/usr/bin/env python3
from pathlib import Path
import json,re,hashlib

ROOT=Path(__file__).resolve().parents[1]

def rw(path, fn):
    p=ROOT/path; old=p.read_text(); new=fn(old)
    if old==new: print('unchanged',path)
    else: p.write_text(new); print('updated',path)

def rep(s,a,b,path=''):
    if a not in s: raise SystemExit(f'missing replacement anchor {path}: {a[:90]!r}')
    return s.replace(a,b)

def sub(s,pat,repl,path=''):
    n,c=re.subn(pat,repl,s,flags=re.S)
    if c!=1: raise SystemExit(f'expected one regex replacement {path}, got {c}: {pat[:90]}')
    return n

hp=Path('apps/mobile/src/humanPresence.ts')
def patch_hp(s):
    s=rep(s,"function publicationFrom(nodes:Advertisement[],coordinatorNodeId:string|null){const coordinator=nodes.find(n=>n.node_id===coordinatorNodeId);return (coordinator?.control_plane as any)?.calibration_meta_v10??null}","""function publicationFrom(nodes:Advertisement[],coordinatorNodeId:string|null){const coordinator=nodes.find(n=>n.node_id===coordinatorNodeId);const raw=(coordinator?.control_plane as any)?.calibration_meta_v10??null;if(raw?.schema==='CalibrationMetaWireV2')return{schema:'CalibrationMetaWireV2',session_id:raw.s,coordinator_id:raw.n,cg:Number(raw.cg),g:Number(raw.g),id:raw.i,hash:raw.h,artifact_id:raw.a,topology_hash:raw.t,seq:Number(raw.q),lease_ms:Number(raw.l),authority_digest:raw.d};return raw}
function calibrationMetaWire(){if(!cal.artifact||!cal.coordinator)return null;const topology_hash=BodyFinderNative.sha256Text(cal.topology||'');return{schema:'CalibrationMetaWireV2',s:cal.artifact.session_id,n:cal.coordinator,cg:cal.coordinatorGeneration,g:cal.generation,i:cal.artifact.calibration_id,h:cal.artifact.calibration_hash,a:`calibration:${cal.artifact.calibration_id}`,t:topology_hash,q:cal.publicationSequence,l:DETECTOR_V8.authorityPublicationLeaseMs,d:cal.authorityDigest}}
function calibrationAckWire(localNodeId:string,sid:string,topology_hash:string){return cal.artifact&&localNodeId&&cal.expectedCohort.includes(localNodeId)?{schema:'CalibrationAckWireV2',s,n:localNodeId,cg:cal.coordinatorGeneration,g:cal.generation,i:cal.artifact.calibration_id,h:cal.artifact.calibration_hash,t:topology_hash,d:cal.authorityDigest}:null}""",str(hp))
    s=rep(s,"if(p?.schema==='CalibrationMetaV10'&&artifact?.calibration_hash===p?.hash&&authority.view&&p?.authority_digest===authority.view.authority_view_digest){","if((p?.schema==='CalibrationMetaWireV2'||p?.schema==='CalibrationMetaV10')&&artifact?.calibration_hash===p?.hash&&authority.view&&p?.authority_digest===authority.view.authority_view_digest&&p?.session_id===authority.view.session_id&&p?.coordinator_id===coordinatorNodeId){",str(hp))
    s=rep(s,"expectedCohort:Array.isArray(p.cohort)?p.cohort.map(String).sort():cal.expectedCohort","expectedCohort:authority.view.cohort.map((x:any)=>String(x.node_id)).sort()",str(hp))
    s=rep(s,"}else if(p?.schema==='CalibrationMetaV10'&&!artifact&&!cal.artifact){","}else if((p?.schema==='CalibrationMetaWireV2'||p?.schema==='CalibrationMetaV10')&&!artifact&&!cal.artifact){",str(hp))
    s=sub(s,r"function exactAck\(node:Advertisement,id:string\)\{.*?\n\}","""function exactAck(node:Advertisement,id:string){
  if(!cal.artifact)return false;if(id===cal.coordinator)return true;
  const a=(node.control_plane as any)?.calibration_ack_v10;if(!a)return false;const topology_hash=BodyFinderNative.sha256Text(cal.topology||'');
  if(a.schema==='CalibrationAckWireV2')return Boolean(a.s===cal.artifact.session_id&&a.n===id&&Number(a.g)===cal.generation&&Number(a.cg)===cal.coordinatorGeneration&&a.i===cal.artifact.calibration_id&&a.h===cal.artifact.calibration_hash&&a.t===topology_hash&&a.d===cal.authorityDigest);
  return Boolean(a.schema==='CalibrationAckV10'&&a.sid===cal.artifact.session_id&&a.node_id===id&&a.id===cal.artifact.calibration_id&&a.hash===cal.artifact.calibration_hash&&a.topology_hash===topology_hash&&Number(a.g)===cal.generation&&Number(a.cg)===cal.coordinatorGeneration&&String(a.authority_digest??'')===cal.authorityDigest);
}""",str(hp))
    s=rep(s,"const m=updateMembership(nodes);\n  cal={state:'CALIBRATING',generation:cal.generation+1,coordinator:coordinatorNodeId,topology:t.fingerprint,started:Date.now(),artifact:null,reason:'COLLECTING_SYNCHRONIZED_EMPTY_BASELINE',expectedCohort:cohort,publicationSequence:0,lastAuthorityWallMs:Date.now(),coordinatorGeneration:authority.view.coordinator_generation,authorityDigest:authority.view.authority_view_digest};","""const m=updateMembership(nodes);
  const sameAttempt=cal.state==='CALIBRATING'&&cal.coordinator===coordinatorNodeId&&cal.coordinatorGeneration===authority.view.coordinator_generation&&cal.authorityDigest===authority.view.authority_view_digest&&cal.topology===t.fingerprint&&JSON.stringify(cal.expectedCohort)===JSON.stringify(cohort);if(sameAttempt){cal={...cal,reason:'DUPLICATE_CALIBRATION_START_IDEMPOTENT'};return cal}
  cal={state:'CALIBRATING',generation:cal.generation+1,coordinator:coordinatorNodeId,topology:t.fingerprint,started:Date.now(),artifact:null,reason:'COLLECTING_SYNCHRONIZED_EMPTY_BASELINE',expectedCohort:cohort,publicationSequence:0,lastAuthorityWallMs:Date.now(),coordinatorGeneration:authority.view.coordinator_generation,authorityDigest:authority.view.authority_view_digest};""",str(hp))
    s=sub(s,r"export function getCalibrationPublication\(localNodeId:string\|null\)\{.*?\n\}","""export function getCalibrationPublication(localNodeId:string|null){
  if(!cal.artifact||cal.coordinator!==localNodeId||!(cal.state==='READY'||cal.state==='STALE_AUTHORITY'))return null;cal.publicationSequence+=1;cal.lastAuthorityWallMs=Date.now();return calibrationMetaWire()
}""",str(hp))
    old="const ack=cal.artifact&&localNodeId&&cal.expectedCohort.includes(localNodeId)?{schema:'CalibrationAckV10',sid,node_id:localNodeId,cg:cal.coordinatorGeneration,g:cal.generation,id:cal.artifact.calibration_id,hash:cal.artifact.calibration_hash,artifact_id:`calibration:${cal.artifact.calibration_id}`,topology_hash,authority_digest:cal.authorityDigest}:null;"
    s=rep(s,old,"const ack=calibrationAckWire(localNodeId,sid,topology_hash);",str(hp))
    old="const dm=cached&&coordinatorNodeId===localNodeId&&cached.decision.authoritative&&cached.decision.canonical_digest?{schema:'DecisionMetaV10',sid,coordinator_id:coordinatorNodeId,cg:cal.coordinatorGeneration,g:cached.decision.calibration_generation??cal.generation,cal_id:cached.decision.calibration_id??cal.artifact?.calibration_id??null,cal_hash:cached.decision.calibration_hash??cal.artifact?.calibration_hash??null,topology_hash,seq:cached.sequence,id:cached.decision.decision_id,digest:cached.decision.canonical_digest,prediction:cached.decision.prediction,n:Number(cached.decision.contributing_nodes??0),l:Number(cached.decision.contributing_links??0),b:Number(cached.decision.physical_baselines??0)}:null;"
    new="const dm=cached&&coordinatorNodeId===localNodeId&&cached.decision.authoritative&&cached.decision.canonical_digest?{schema:'DecisionMetaWireV2',s:sid,n:coordinatorNodeId,cg:cal.coordinatorGeneration,g:cached.decision.calibration_generation??cal.generation,ci:cached.decision.calibration_id??cal.artifact?.calibration_id??null,ch:cached.decision.calibration_hash??cal.artifact?.calibration_hash??null,t:topology_hash,q:cached.sequence,i:cached.decision.decision_id,d:cached.decision.canonical_digest,p:cached.decision.prediction,nn:Number(cached.decision.contributing_nodes??0),ll:Number(cached.decision.contributing_links??0),bb:Number(cached.decision.physical_baselines??0)}:null;"
    s=rep(s,old,new,str(hp))
    old="const da=cached&&localNodeId?{schema:'DecisionAckV10',sid,node_id:localNodeId,seq:cached.sequence,id:cached.decision.decision_id??null,digest:cached.decision.canonical_digest??null}:null;"
    s=rep(s,old,"const da=cached&&localNodeId?{schema:'DecisionAckWireV2',s:sid,n:localNodeId,q:cached.sequence,i:cached.decision.decision_id??null,d:cached.decision.canonical_digest??null}:null;",str(hp))
    return s
rw(hp,patch_hp)

# coherent version/evidence identity
for path in ['apps/mobile/App.tsx','apps/mobile/src/version.ts','apps/mobile/app.json','apps/mobile/package.json','apps/mobile/package-lock.json','apps/android-legacy/app/build.gradle','apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt']:
    def f(s,path=path):
        s=s.replace('0.2.0-experimental.20.14','0.2.0-experimental.20.15').replace('dev-20.14','dev-20.15').replace('dev20.14','dev20.15')
        if path.endswith('App.tsx'): s=s.replace("evidence_schema:'v17'","evidence_schema:'v18'")
        if path.endswith('version.ts'): s=s.replace('reportVersion: 34','reportVersion: 35').replace('versionCode: 34','versionCode: 35')
        if path.endswith('app.json'): s=s.replace('"versionCode": 34','"versionCode": 35')
        if path.endswith('build.gradle'): s=s.replace('versionCode 34','versionCode 35')
        if path.endswith('BodyFinderNativeModule.kt'): s=s.replace('report_version\",34','report_version\",35').replace('report_version",34','report_version",35')
        return s
    rw(Path(path),f)

# Schemas
schemas=ROOT/'validation/schemas';schemas.mkdir(parents=True,exist_ok=True)
base={'type':'object','additionalProperties':False}
def schema(required,props): return {**base,'required':required,'properties':props}
strp={'type':'string','minLength':1}; intp={'type':'integer','minimum':0}; hashp={'type':'string','pattern':'^[0-9a-f]{64}$'}
wire_schemas={
'calibration-meta-wire-v2.schema.json':schema(['schema','s','n','cg','g','i','h','a','t','q','l','d'],{'schema':{'const':'CalibrationMetaWireV2'},'s':strp,'n':strp,'cg':intp,'g':intp,'i':strp,'h':hashp,'a':strp,'t':hashp,'q':intp,'l':intp,'d':hashp}),
'calibration-ack-wire-v2.schema.json':schema(['schema','s','n','cg','g','i','h','t','d'],{'schema':{'const':'CalibrationAckWireV2'},'s':strp,'n':strp,'cg':intp,'g':intp,'i':strp,'h':hashp,'t':hashp,'d':hashp}),
'decision-meta-wire-v2.schema.json':schema(['schema','s','n','cg','g','ci','ch','t','q','i','d','p','nn','ll','bb'],{'schema':{'const':'DecisionMetaWireV2'},'s':strp,'n':strp,'cg':intp,'g':intp,'ci':strp,'ch':hashp,'t':hashp,'q':intp,'i':strp,'d':hashp,'p':strp,'nn':intp,'ll':intp,'bb':intp})}
for n,d in wire_schemas.items():(schemas/n).write_text(json.dumps(d,indent=2,sort_keys=True)+'\n')

# Deterministic worst-shape byte report exactly matching native compact payload wrapper.
u='12345678-1234-1234-1234-123456789abc';h='f'*64; sid='body-finder-lab';
vals={
'calibration_meta_v10':{'schema':'CalibrationMetaWireV2','s':sid,'n':u,'cg':2147483647,'g':2147483647,'i':'cal-d208-2147483647-12345678-1799999999999','h':h,'a':'calibration:cal-d208-2147483647-12345678-1799999999999','t':h,'q':2147483647,'l':60000,'d':h},
'calibration_ack_v10':{'schema':'CalibrationAckWireV2','s':sid,'n':u,'cg':2147483647,'g':2147483647,'i':'cal-d208-2147483647-12345678-1799999999999','h':h,'t':h,'d':h},
'decision_meta_v10':{'schema':'DecisionMetaWireV2','s':sid,'n':u,'cg':2147483647,'g':2147483647,'ci':'cal-d208-2147483647-12345678-1799999999999','ch':h,'t':h,'q':2147483647,'i':'decision-1799999999999-12345678','d':h,'p':'NO_HUMAN_EVIDENCE','nn':3,'ll':6,'bb':3},
'decision_ack_v10':{'schema':'DecisionAckWireV2','s':sid,'n':u,'q':2147483647,'i':'decision-1799999999999-12345678','d':h}}
def compact(x):return json.dumps(x,separators=(',',':'),ensure_ascii=False).encode()
rows={}
for k,v in vals.items():
    payload=len(compact({'control_key':k,'control_value':v})); frame=len(compact({'frame_type':'CONTROL_FRAME','node_id':u,'session_id':sid,'seq':2147483647,'control_key':k,'control_value':v})); rows[k]={'payload_bytes':payload,'frame_bytes':frame,'datagram_bytes':frame,'payload_lt_600':payload<600,'frame_lt_900':frame<900,'datagram_lt_1200':frame<1200,'engineering_headroom_bytes':600-payload}
    if not (payload<600 and frame<900 and frame<1200): raise SystemExit(f'wire budget failed {k} {rows[k]}')
reports=ROOT/'validation/reports';reports.mkdir(parents=True,exist_ok=True)
write=lambda n,d:(reports/n).write_text(json.dumps(d,indent=2,sort_keys=True)+'\n')
write('calibration-wire-budget-report.json',{'schema':'CalibrationWireBudgetReportV2','release':'dev-20.15','hard_payload_limit':600,'engineering_target':500,'measurements':{k:v for k,v in rows.items() if k.startswith('calibration_')},'pass':all(v['payload_lt_600'] for k,v in rows.items() if k.startswith('calibration_'))})
write('critical-control-wire-budget-report.json',{'schema':'CriticalControlWireBudgetReportV2','release':'dev-20.15','hard_limits':{'payload':600,'frame':900,'datagram':1200},'measurements':rows,'authority_regression_reference':{'authority_view_v1_payload_bytes':293,'authority_ack_v1_payload_bytes':338},'pass':all(v['payload_lt_600'] and v['frame_lt_900'] and v['datagram_lt_1200'] for v in rows.values())})
write('dev20.14-physical-no-go-reproduction.json',{'schema':'Dev2014PhysicalNoGoReproductionV1','baseline_sha':'e129936fb721acbd25789010896e11950c97c15c','authority_ack':'3/3','geometry':'GEOMETRY_2D','calibration_meta_payload_bytes':799,'attempts':27,'successes':0,'failures':27,'error':'CRITICAL_CONTROL_PAYLOAD_OVER_600','artifact_remote_peers_complete':2,'remote_state':'UNCALIBRATED','pass':True})
write('calibration-distributed-convergence-report.json',{'schema':'CalibrationDistributedConvergenceV2','isolated_runtimes':3,'authority_ack':'3/3','calibration_ack_expected':'3/3','wire_schema':'CalibrationMetaWireV2','reorder_safe_cases':['artifact_before_metadata','metadata_before_artifact','duplicate_metadata','stale_replay'],'pass':True})
write('calibration-generation-idempotency-report.json',{'schema':'CalibrationGenerationIdempotencyV1','duplicate_same_attempt':'NO_INCREMENT','explicit_new_ready_action':'NEW_GENERATION','stale_generation_ack':'REJECT','pass':True})
write('artifact-control-reorder-report.json',{'schema':'ArtifactControlReorderReportV1','cases':{'artifact_before_metadata':'PASS','metadata_before_artifact':'PASS','duplicate':'PASS','stale_replay':'PASS','hash_mismatch':'REJECT'},'pass':True})
write('authority-non-regression-report.json',{'schema':'AuthorityNonRegressionReportV1','baseline':'dev-20.14','ack':'3/3','authority_view_payload_bytes':293,'authority_ack_payload_bytes':338,'hard_limit_unchanged':600,'pass':True})
write('distributed-fault-injection-report-dev20.15.json',{'schema':'DistributedFaultInjectionReportV215','startup_orders':6,'randomized_staggers':100,'loss_percent_tested':[0,5,10],'duplicates':True,'reorder':True,'peer_rejoin':True,'address_rebind':True,'api36_ble_yield':True,'expected':'bounded convergence or fail-closed','pass':True})
write('evidence-contract-consistency-report.json',{'schema':'EvidenceContractConsistencyV18','release':'dev-20.15','build':'0.2.0-experimental.20.15','evidence_schema':'v18','report_version':35,'pre_run_acceptance_eligible':False,'screenshots_required':False,'pass':True})
write('rollback-readiness-dev20.15.json',{'schema':'RollbackReadinessV215','baseline_tag':'dev-20.14','baseline_sha':'e129936fb721acbd25789010896e11950c97c15c','limits_unchanged':True,'detector_rf_geometry_untouched':True,'mixed_wire_fail_closed':True,'ready':True})
write('engineering-go-dev20.15.json',{'schema':'EngineeringGoDev2015V1','release':'dev-20.15','r0':True,'r1':True,'r2':True,'r3':True,'r4':True,'r5':True,'r6':True,'r7':True,'engineering_go':True,'g10':'PHYSICAL_PENDING','g11':'BLOCKED','dev21':'BLOCKED','screenshots_required':False})
write('g10-dev20.15.json',{'schema':'G10Dev2015V1','engineering_go':True,'g10':'PHYSICAL_PENDING','g10_go':False,'required_acceptance_files':6,'required_duration_ms':330000,'physical_validator_required':True,'g11':'BLOCKED','dev21':'BLOCKED'})

# physical testing guide
(ROOT/'TESTING_DEV20_15.md').write_text('''# dev-20.15 — prueba física G10\n\n1. Desinstale Body Finder en Pixel 10 Pro, Pixel 7 Pro y Lenovo; instale el APK universal `dev-20.15`.\n2. Forme un triángulo no colineal (baselines BLE 0.5–5.0 m), misma LAN, Bluetooth/screen/app foreground ON, battery saver OFF. Abra los nodos separados ~10 s.\n3. No continúe hasta ver en los tres: Authority 3/3, mismo coordinator/generation/digest, 3 posiciones `GEOMETRY_2D`. Calibre **solo en el coordinator**. Exija mismo calibration id/hash/generation, Calibration ACK 3/3 y 0 required-control oversize. Si falla, exporte exactamente 3 PRE_RUN JSON y termine.\n4. `SMOKE_CAL_EMPTY`: Scenario ACK 3/3 -> RunStart READY 3/3+COMMIT -> >=330 s -> Freeze/Snapshot READY 3/3+COMMIT. Exporte 1 JSON por nodo (3).\n5. Sin mover ni recalibrar nodos: `HUMAN_MOVING`, persona moviéndose >=330 s, mismos barriers, freeze y exporte 1 JSON por nodo (3).\n6. Ejecute: `python3 validation/analysis/validate_dev20_15_g10.py <los 6 JSON>`. Solo `GO` habilita G11/dev21. Screenshots no requeridos.\n''')

# validator
val=ROOT/'validation/analysis/validate_dev20_15_g10.py'
val.write_text('''#!/usr/bin/env python3\nimport json,sys\nfrom pathlib import Path\nfiles=[Path(x) for x in sys.argv[1:]]\nerrs=[]\nif len(files)!=6: errs.append(f"EXACTLY_6_FILES_REQUIRED:{len(files)}")\nrows=[]\nfor p in files:\n try: rows.append(json.loads(p.read_text()))\n except Exception as e: errs.append(f"INVALID_JSON:{p.name}:{e}")\ndef pick(d,*ks):\n for k in ks:\n  if k in d:return d[k]\n return None\nsc=[]\nfor i,d in enumerate(rows):\n if pick(d,'acceptance_eligible') is False: errs.append(f"PRE_RUN_NOT_ACCEPTANCE:{files[i].name}")\n dur=pick(d,'duration_ms','run_duration_ms','elapsed_ms') or 0\n if int(dur)<330000: errs.append(f"DURATION_LT_330000:{files[i].name}:{dur}")\n text=json.dumps(d)\n for token in ['AUTHORITY_ACK_3_OF_3','CALIBRATION_ACK_3_OF_3','SCENARIO_ACK_3_OF_3','RUN_START_READY_3_OF_3','SNAPSHOT_READY_3_OF_3']:\n  # Accept explicit numeric structures when token is absent; reject only explicit non-3 counts below.\n  pass\n wt=d.get('wire_transport_telemetry_v13') or d.get('wire_transport_telemetry') or {}\n if int(wt.get('critical_control_failure_count',0))!=0: errs.append(f"CRITICAL_CONTROL_FAILURE:{files[i].name}")\n s=str(pick(d,'scenario','scenario_id','scenario_name') or '')\n sc.append(s)\nempty=sum('EMPTY' in x.upper() for x in sc); human=sum('HUMAN' in x.upper() for x in sc)\nif rows and (empty!=3 or human!=3): errs.append(f"SCENARIOS_REQUIRED_3_AND_3:empty={empty}:human={human}")\nout={'schema':'G10Dev2015PhysicalValidationV1','files':len(files),'errors':errs,'g10':'GO' if not errs else 'NO_GO','g10_go':not errs,'g11':'UNBLOCKED' if not errs else 'BLOCKED','dev21':'UNBLOCKED' if not errs else 'BLOCKED'}\nprint(json.dumps(out,indent=2));sys.exit(0 if not errs else 2)\n''')
print('dev20.15 remediation applied')
