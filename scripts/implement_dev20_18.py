#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def read(path:str)->str:return (ROOT/path).read_text(encoding='utf-8')
def write(path:str,text:str):
    p=ROOT/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')
def replace_once(path:str,old:str,new:str):
    text=read(path)
    if new in text and old not in text:return
    count=text.count(old)
    if count!=1:raise RuntimeError(f'{path}: expected exactly one baseline pattern, found {count}: {old[:120]!r}')
    write(path,text.replace(old,new,1))

def patch_authority():
    p='apps/mobile/src/authority.ts'
    replace_once(p,
      "type State={baseDigest:string|null;generation:number;pinned:boolean;pinnedView:AuthorityViewV1|null};",
      "type PinEvent={wall_ms:number;kind:'PIN'|'UNPIN';cohort_digest:string|null;reason:string};\ntype State={baseDigest:string|null;generation:number;pinned:boolean;pinnedView:AuthorityViewV1|null;pinnedCohortDigest:string|null;pinInvalidatedReason:string|null;pinHistory:PinEvent[]};")
    replace_once(p,
      "function state(sid:string){let s=states.get(sid);if(!s){s={baseDigest:null,generation:0,pinned:false,pinnedView:null};states.set(sid,s)}return s}",
      "function state(sid:string){let s=states.get(sid);if(!s){s={baseDigest:null,generation:0,pinned:false,pinnedView:null,pinnedCohortDigest:null,pinInvalidatedReason:null,pinHistory:[]};states.set(sid,s)}return s}\nfunction pinEvent(s:State,kind:'PIN'|'UNPIN',cohortDigest:string|null,reason:string){s.pinHistory=[...s.pinHistory,{wall_ms:Date.now(),kind,cohort_digest:cohortDigest,reason}].slice(-64)}")
    replace_once(p,
      "function compute(nodes:Advertisement[]):AuthorityViewV1|null{const sid=currentSession(nodes),s=state(sid);if(s.pinned&&s.pinnedView)return s.pinnedView;const cohortNodes=completeCohort(nodes,sid);if(!cohortNodes)return null;const cohort=cohortNodes.map(n=>({node_id:String(n.node_id),instance_epoch:epochOf(n)!}));",
      "function compute(nodes:Advertisement[]):AuthorityViewV1|null{const sid=currentSession(nodes),s=state(sid);const cohortNodes=completeCohort(nodes,sid);if(!cohortNodes){if(s.pinned){pinEvent(s,'UNPIN',s.pinnedCohortDigest,'CURRENT_COHORT_INCOMPLETE');s.pinned=false;s.pinnedView=null;s.pinnedCohortDigest=null;s.pinInvalidatedReason='CURRENT_COHORT_INCOMPLETE';s.baseDigest=null}return null}const cohort=cohortNodes.map(n=>({node_id:String(n.node_id),instance_epoch:epochOf(n)!}));const observedCohortDigest=sha({session_id:sid,cohort});if(s.pinned&&s.pinnedView){const pinnedDigest=s.pinnedCohortDigest??sha({session_id:sid,cohort:s.pinnedView.cohort});if(pinnedDigest===observedCohortDigest)return s.pinnedView;pinEvent(s,'UNPIN',pinnedDigest,'COHORT_OR_INSTANCE_EPOCH_CHANGED');s.pinned=false;s.pinnedView=null;s.pinnedCohortDigest=null;s.pinInvalidatedReason='COHORT_OR_INSTANCE_EPOCH_CHANGED';s.baseDigest=null}")
    replace_once(p,
      "if(committed){s.pinned=true;s.pinnedView=view}return view}",
      "if(committed){if(!s.pinned||s.pinnedCohortDigest!==observedCohortDigest)pinEvent(s,'PIN',observedCohortDigest,'CURRENT_RUNSTART_COMMIT');s.pinned=true;s.pinnedView=view;s.pinnedCohortDigest=observedCohortDigest;s.pinInvalidatedReason=null}return view}")
    replace_once(p,
      "return{schema:'AuthorityStatusV2',view,canonical_cohort_input:view.cohort,base_digest:view.base_digest,authority_view_digest:view.authority_view_digest,coordinator_generation:view.coordinator_generation,",
      "const authority_pin_state=s.pinned?'PINNED':'UNPINNED';return{schema:'AuthorityStatusV2',view,canonical_cohort_input:view.cohort,base_digest:view.base_digest,authority_view_digest:view.authority_view_digest,coordinator_generation:view.coordinator_generation,authority_pin_state,pinned_identity_digest:s.pinnedCohortDigest,pin_invalidated_reason:s.pinInvalidatedReason,pin_history:s.pinHistory,")

def patch_native_store():
    p='apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt'
    replace_once(p,
      '  @Synchronized private fun cachedArtifact(id:String):CachedArtifact?=artifactCache[id]\n',
      '  @Synchronized private fun cachedArtifact(id:String):CachedArtifact?=artifactCache[id]\n  @Synchronized fun verifiedArtifactJson(id:String):String?{val a=artifactCache[id]?:return null;return JSONObject().put("artifact_id",id).put("artifact_sha256",a.sha).put("complete",true).put("source_node_id",a.sourceNode).put("source_generation",a.generation).put("artifact_type",a.artifactType).put("payload",JSONObject(a.payload.toString())).toString()}\n')
    replace_once(p,
      '    Function("getCalibrationSnapshotJson") {\n      calibrationSnapshot().toString()\n    }\n',
      '    Function("getCalibrationSnapshotJson") {\n      calibrationSnapshot().toString()\n    }\n    Function("getVerifiedArtifactJson") { artifactId: String ->\n      WireTransportV10.verifiedArtifactJson(artifactId)\n    }\n')
    p='apps/mobile/modules/body-finder-native/index.ts'
    replace_once(p,
      '  evaluateHumanPresenceJson(inputJson: string): string; sha256Text(text: string): string;\n',
      '  evaluateHumanPresenceJson(inputJson: string): string; sha256Text(text: string): string; getVerifiedArtifactJson(artifactId: string): string | null;\n')
    replace_once(p,"const EVIDENCE_SCHEMA='dev20.13-self-contained-json-evidence-v16';","const EVIDENCE_SCHEMA='dev20.18-state-lifecycle-json-evidence-v20';")

def patch_calibration():
    p='apps/mobile/src/humanPresence.ts'
    replace_once(p,
      "function artifactFrom(node:Advertisement|undefined,id:string|null|undefined){if(!node||!id)return null;return (node as any)?.artifact_cache_v1?.[id]??null}",
      "function canonicalArtifact(v:any):string{if(v===null||typeof v!=='object')return JSON.stringify(v);if(Array.isArray(v))return'['+v.map(canonicalArtifact).join(',')+']';return'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonicalArtifact(v[k])).join(',')+'}'}\nfunction verifiedLocalArtifact(id:string|null|undefined,advertisedSha:string|null|undefined){if(!id||!advertisedSha)return null;try{const raw=BodyFinderNative.getVerifiedArtifactJson(id);if(!raw)return null;const r=JSON.parse(raw);if(r?.complete!==true||r?.artifact_id!==id||String(r?.artifact_sha256??'')!==String(advertisedSha)||!r?.payload)return null;if(BodyFinderNative.sha256Text(canonicalArtifact(r.payload))!==String(advertisedSha))return null;return r}catch{return null}}")
    replace_once(p,
      "artifact_id:`calibration:${raw.i}`,topology_hash:raw.t,seq:Number(raw.q),lease_ms:Number(raw.l),authority_digest:raw.d}",
      "artifact_id:`calibration:${raw.i}`,artifact_sha256:String(raw.artifact_sha256??''),topology_hash:raw.t,seq:Number(raw.q),lease_ms:Number(raw.l),authority_digest:raw.d}")
    replace_once(p,
      "const artifact=p?.artifact_id?artifactFrom(coordinator,p.artifact_id):null;\n  if(p?.schema==='CalibrationMetaWireV3'&&artifact?.calibration_hash===p?.hash&&authority.view",
      "const localVerified=p?.artifact_id?verifiedLocalArtifact(p.artifact_id,p?.artifact_sha256):null,artifact=localVerified?.payload??null;\n  if(p?.schema==='CalibrationMetaWireV3'&&localVerified?.complete===true&&artifact?.calibration_hash===p?.hash&&String(artifact?.calibration_id??'')===String(p?.id??'')&&authority.view")
    replace_once(p,
      "reason:'AUTHORITATIVE_CALIBRATION_FINAL_V10_COMPLETE'",
      "reason:'AUTHORITATIVE_CALIBRATION_LOCAL_RECEIVER_VERIFIED_PROMOTED'")
    replace_once(p,
      "return{state:cal.state,generation:cal.generation,calibration_generation:cal.generation,coordinator_generation:cal.coordinatorGeneration,authority_digest:cal.authorityDigest,authority_consensus:authority.consensus,authority_ack_count:authority.ack_count,coordinator_node_id:cal.coordinator,topology_fingerprint:cal.topology,topology_hash:topologyHash,topology_hash_source:cal.topologyHash?'COORDINATOR_CANONICAL_OR_ECHO':'LOCAL_FINGERPRINT_HASH_ONCE',expected_cohort:cal.expectedCohort,started_wall_ms:cal.started,calibration_id:cal.artifact?.calibration_id??null,calibration_hash:cal.artifact?.calibration_hash??null,reason:cal.reason,publication_sequence:cal.publicationSequence,",
      "const binding=cal.artifact?BodyFinderNative.sha256Text(canonicalArtifact({session_id:currentSession(nodes),coordinator_id:cal.coordinator,coordinator_generation:cal.coordinatorGeneration,calibration_generation:cal.generation,calibration_id:cal.artifact.calibration_id,calibration_hash:cal.artifact.calibration_hash,topology_hash:topologyHash,authority_digest:cal.authorityDigest})):null,historicalNotCounted=matrix.filter((x:any)=>!x.acknowledged&&x.ack_schema).length;return{state:cal.state,generation:cal.generation,calibration_generation:cal.generation,coordinator_generation:cal.coordinatorGeneration,authority_digest:cal.authorityDigest,authority_consensus:authority.consensus,authority_ack_count:authority.ack_count,coordinator_node_id:cal.coordinator,topology_fingerprint:cal.topology,topology_hash:topologyHash,topology_hash_source:cal.topologyHash?'COORDINATOR_CANONICAL_OR_ECHO':'LOCAL_FINGERPRINT_HASH_ONCE',expected_cohort:cal.expectedCohort,started_wall_ms:cal.started,calibration_id:cal.artifact?.calibration_id??null,calibration_hash:cal.artifact?.calibration_hash??null,current_calibration_binding_digest:binding,current_calibration_ack_count:ackCount,historical_ack_not_counted:historicalNotCounted,local_artifact_promoted:Boolean(cal.artifact&&cal.state==='READY'),artifact_promotion_state:cal.artifact?(cal.state==='READY'?'PROMOTED':'PRESERVED'):'MISSING',artifact_promotion_source:cal.coordinator===lastLocalNodeId?'LOCAL_COORDINATOR':'LOCAL_RECEIVER_VERIFIED',reason:cal.reason,publication_sequence:cal.publicationSequence,")

def patch_campaign():
    p='apps/mobile/src/campaignControl.ts'
    replace_once(p,
      "type State={authorityDigest:string|null;command:ScenarioCommandV1|null;commandGeneration:number;runOrdinal:number;startPrepare:RunStartPrepareV1|null;startCommit:RunStartCommitV1|null;freezePrepare:RunFreezePrepareV2|null;freezeCommit:RunFreezeCommitV2|null};",
      "type InvalidationEvent={wall_ms:number;old_binding_digest:string|null;new_binding_digest:string|null;reason:string};\ntype State={authorityDigest:string|null;command:ScenarioCommandV1|null;commandGeneration:number;runOrdinal:number;startGeneration:number;startContextDigest:string|null;invalidationHistory:InvalidationEvent[];startPrepare:RunStartPrepareV1|null;startCommit:RunStartCommitV1|null;freezePrepare:RunFreezePrepareV2|null;freezeCommit:RunFreezeCommitV2|null};")
    replace_once(p,
      "function fresh():State{return{authorityDigest:null,command:null,commandGeneration:0,runOrdinal:0,startPrepare:null,startCommit:null,freezePrepare:null,freezeCommit:null}}",
      "function fresh():State{return{authorityDigest:null,command:null,commandGeneration:0,runOrdinal:0,startGeneration:0,startContextDigest:null,invalidationHistory:[],startPrepare:null,startCommit:null,freezePrepare:null,freezeCommit:null}}")
    replace_once(p,
      "function bind(nodes:Advertisement[],localId:string|null,s:State){const a=getAuthorityStatus(nodes,localId),digest=a.view?.authority_view_digest??null;if(s.authorityDigest&&digest&&s.authorityDigest!==digest&&!s.startCommit){s.command=null;s.startPrepare=null;s.startCommit=null;s.freezePrepare=null;s.freezeCommit=null}s.authorityDigest=digest;return a}",
      "function invalidateStart(s:State,newDigest:string|null,reason:string){const old=s.startContextDigest;if(old||s.startPrepare||s.startCommit||s.freezePrepare||s.freezeCommit)s.invalidationHistory=[...s.invalidationHistory,{wall_ms:Date.now(),old_binding_digest:old,new_binding_digest:newDigest,reason}].slice(-64);s.startPrepare=null;s.startCommit=null;s.freezePrepare=null;s.freezeCommit=null}\nfunction bind(nodes:Advertisement[],localId:string|null,s:State){const a=getAuthorityStatus(nodes,localId),digest=a.view?.authority_view_digest??null;if(s.authorityDigest!==null&&s.authorityDigest!==digest){s.command=null;invalidateStart(s,null,'AUTHORITY_VIEW_CHANGED');s.startContextDigest=null}s.authorityDigest=digest;return a}")
    replace_once(p,
      "function calibrationIdentity(cal:any){return{calibration_id:String(cal?.calibration_id??''),calibration_hash:String(cal?.calibration_hash??''),calibration_generation:Number(cal?.calibration_generation??cal?.generation??0),topology_hash:topologyHash(cal)}}",
      "function calibrationIdentity(cal:any){return{calibration_id:String(cal?.calibration_id??''),calibration_hash:String(cal?.calibration_hash??''),calibration_generation:Number(cal?.calibration_generation??cal?.generation??0),topology_hash:topologyHash(cal)}}\nfunction startContext(nodes:Advertisement[],s:State,cal:any,a:any){if(!a.view||!s.command)return null;const ci=calibrationIdentity(cal);if(!ci.calibration_id||!ci.calibration_hash||!ci.topology_hash)return null;return sha({session_id:session(nodes),calibration:ci,authority_view_digest:a.view.authority_view_digest,coordinator_generation:a.view.coordinator_generation,scenario_digest:s.command.command_digest,scenario_generation:s.command.scenario_generation,cohort:a.view.cohort})}\nfunction bindStartContext(nodes:Advertisement[],s:State,cal:any,a:any){const next=startContext(nodes,s,cal,a);if(!next){if(s.startContextDigest||s.startPrepare||s.startCommit||s.freezePrepare||s.freezeCommit)invalidateStart(s,null,'RUN_BINDING_UNAVAILABLE');s.startContextDigest=null;return null}if(s.startContextDigest&&s.startContextDigest!==next)invalidateStart(s,next,'RUN_BINDING_CHANGED');s.startContextDigest=next;return next}")
    replace_once(p,
      "s.startPrepare=null;s.startCommit=null;s.freezePrepare=null;s.freezeCommit=null}}",
      "invalidateStart(s,null,'SCENARIO_CHANGED');s.startContextDigest=null}}")
    replace_once(p,
      "s.startPrepare=null;s.startCommit=null;s.freezePrepare=null;s.freezeCommit=null;return s.command}",
      "invalidateStart(s,null,'SCENARIO_CHANGED');s.startContextDigest=null;return s.command}")
    replace_once(p,
      "function syncStart(nodes:Advertisement[],coordinatorId:string|null,localId:string|null,cal:any){const s=st(nodes,localId),a=bind(nodes,localId,s);if(!a.view||!coordinatorId||coordinatorId===localId)return;",
      "function syncStart(nodes:Advertisement[],coordinatorId:string|null,localId:string|null,cal:any){const s=st(nodes,localId),a=bind(nodes,localId,s);if(!a.view||!bindStartContext(nodes,s,cal,a)||!coordinatorId||coordinatorId===localId)return;")
    replace_once(p,
      "function localStartReady(nodes:Advertisement[],localId:string|null,cal:any):RunStartReadyV1|null{const s=st(nodes,localId),a=bind(nodes,localId,s),p=s.startPrepare;if(!p||!localId||!a.view||!a.consensus)return null;const ci=calibrationIdentity(cal);if(String(cal?.state)!=='READY'&&String(cal?.state)!=='STALE_AUTHORITY')return null;",
      "function localStartReady(nodes:Advertisement[],localId:string|null,cal:any):RunStartReadyV1|null{const s=st(nodes,localId),a=bind(nodes,localId,s);if(!bindStartContext(nodes,s,cal,a))return null;const p=s.startPrepare;if(!p||!localId||!a.view||!a.consensus)return null;const ci=calibrationIdentity(cal);if(String(cal?.state)!=='READY')return null;")
    replace_once(p,
      "const generation=(s.startPrepare?.generation??0)+1,issued_wall_ms=Date.now(),campaign_run_token=sha({",
      "if(!bindStartContext(nodes,s,cal,a))throw new Error('RUN_START_BINDING_UNAVAILABLE');s.startGeneration+=1;const generation=s.startGeneration,issued_wall_ms=Date.now(),campaign_run_token=sha({")
    replace_once(p,
      "const s=st(nodes,localId),a=bind(nodes,localId,s),ids=cohort(nodes),local=localStartReady(nodes,localId,cal),ready:RunStartReadyV1[]=",
      "const s=st(nodes,localId),a=bind(nodes,localId,s);bindStartContext(nodes,s,cal,a);const ids=cohort(nodes),local=localStartReady(nodes,localId,cal),ready:RunStartReadyV1[]=",
      )
    replace_once(p,
      "function syncFreeze(nodes:Advertisement[],coordinatorId:string|null,localId:string|null,authority:any,cal:any){const s=st(nodes,localId),a=bind(nodes,localId,s);if(!a.view||!coordinatorId||coordinatorId===localId)return;",
      "function syncFreeze(nodes:Advertisement[],coordinatorId:string|null,localId:string|null,authority:any,cal:any){const s=st(nodes,localId),a=bind(nodes,localId,s);if(!a.view||!bindStartContext(nodes,s,cal,a)||!s.startCommit||!coordinatorId||coordinatorId===localId)return;")
    replace_once(p,
      "function localFreezeReady(nodes:Advertisement[],coordinatorId:string|null,localId:string|null,cal:any):SnapshotReadyV2|null{const s=st(nodes,localId),a=bind(nodes,localId,s),p=s.freezePrepare;",
      "function localFreezeReady(nodes:Advertisement[],coordinatorId:string|null,localId:string|null,cal:any):SnapshotReadyV2|null{const s=st(nodes,localId),a=bind(nodes,localId,s);if(!bindStartContext(nodes,s,cal,a))return null;const p=s.freezePrepare;")
    replace_once(p,
      "return{schema:'RunStartBarrierV1',wire_schema:'RunStartWireV2',authority_view_digest:a.view?.authority_view_digest??null,authority_ack_count:a.ack_count,prepare:s.startPrepare,",
      "return{schema:'RunStartBarrierV1',wire_schema:'RunStartWireV2',authority_view_digest:a.view?.authority_view_digest??null,authority_ack_count:a.ack_count,run_binding_digest:s.startContextDigest,invalidation_history:s.invalidationHistory,prepare:s.startPrepare,")
    replace_once(p,
      "return{schema:'SnapshotFreezeV2',wire_schema:'RunFreezeWireV3',authority_view_digest:a.view?.authority_view_digest??null,prepare:s.freezePrepare,",
      "return{schema:'SnapshotFreezeV2',wire_schema:'RunFreezeWireV3',authority_view_digest:a.view?.authority_view_digest??null,run_binding_digest:s.startContextDigest,invalidation_history:s.invalidationHistory,prepare:s.freezePrepare,")

def patch_versions_and_assets():
    p='apps/mobile/src/version.ts';t=read(p).replace('0.2.0-experimental.20.17','0.2.0-experimental.20.18').replace('reportVersion: 37','reportVersion: 38').replace('versionCode: 37','versionCode: 38').replace("releaseIteration: 'experimental.20.17'","releaseIteration: 'experimental.20.18'").replace('snapshotSchemaVersion: 16','snapshotSchemaVersion: 20');write(p,t)
    p='apps/mobile/app.json';d=json.loads(read(p));d['expo']['version']='0.2.0-experimental.20.18';d['version']='0.2.0-experimental.20.18';d['expo']['extra']['releaseIteration']='experimental.20.18';d['expo']['android']['versionCode']=38;d['android']['versionCode']=38;write(p,json.dumps(d,indent=2,ensure_ascii=False)+'\n')
    for src,dst in [('validation/analysis/validate_dev20_17_prerun.py','validation/analysis/validate_dev20_18_prerun.py'),('validation/analysis/validate_dev20_17_g10.py','validation/analysis/validate_dev20_18_g10.py')]:
        t=read(src).replace('dev-20.17','dev-20.18').replace('dev20.17','dev20.18').replace('Dev2017','Dev2018')
        if 'prerun' in dst:
            needle="        ca=ai(first(d,'peer_ack_count','calibration_ack_count','calibration_ack_ready_count'))\n"
            ins=needle+"        state=s(first(d,'calibration_state','state')).upper();dist=ab(first(d,'distributed_calibration_ready'));promoted=ab(first(d,'local_artifact_promoted'));binding=s(first(d,'current_calibration_binding_digest'))\n        if state!='READY':errs.append(f'CURRENT_CALIBRATION_READY_REQUIRED:{p.name}:{state}')\n        if not dist:errs.append(f'DISTRIBUTED_CALIBRATION_READY_REQUIRED:{p.name}')\n        if not promoted:errs.append(f'LOCAL_VERIFIED_ARTIFACT_PROMOTED_REQUIRED:{p.name}')\n        if binding and not HEX64.fullmatch(binding):errs.append(f'CURRENT_CALIBRATION_BINDING_SHA256_REQUIRED:{p.name}')\n"
            if needle not in t:raise RuntimeError('prerun validator insertion anchor missing')
            t=t.replace(needle,ins,1)
        write(dst,t)
    testing='''# TESTING DEV-20.18\n\n1. Clean-install `BodyFinder-dev20.18-universal.apk` on exactly 3 Androids.\n2. Wait for peers **2/2**, Authority **3/3** and `GEOMETRY_2D`.\n3. Calibrate EMPTY **once on coordinator only**.\n4. Continue only when all 3 show the same **current** calibration ID/hash/generation/topology, local artifact promoted, Calibration ACK **3/3** and `distributed_calibration_ready=true`.\n5. Issue `SMOKE_CAL_EMPTY`; require Scenario **3/3**.\n6. Press Start once on coordinator; require a **fresh** RunStart **3/3 + COMMIT** bound to the current calibration.\n7. If any pre-run gate fails, export exactly **3 PRE_RUN JSONs** and STOP.\n8. Otherwise run EMPTY >=330 s; End on coordinator; require Freeze **3/3**; export 3 JSONs.\n9. Without moving/recalibrating, run `HUMAN_MOVING` >=330 s; Freeze **3/3**; export 3 JSONs.\n10. Run `python validate_dev20_18_g10.py <exactly six JSONs>`. Share JSON + verdict only; screenshots are unnecessary.\n'''
    write('TESTING_DEV20_18.md',testing)

def main():
    # Deterministic baseline reproduction: these are the exact three dev-20.17 vulnerable source signatures.
    baseline={'remote_artifact_ownership':'artifactFrom(coordinator,p.artifact_id)' in read('apps/mobile/src/humanPresence.ts'),'permanent_authority_pin':'if(s.pinned&&s.pinnedView)return s.pinnedView' in read('apps/mobile/src/authority.ts'),'commit_blocks_authority_invalidation':'s.authorityDigest!==digest&&!s.startCommit' in read('apps/mobile/src/campaignControl.ts'),'stale_authority_local_ready':"String(cal?.state)!=='READY'&&String(cal?.state)!=='STALE_AUTHORITY'" in read('apps/mobile/src/campaignControl.ts')}
    if not all(baseline.values()) and 'verifiedLocalArtifact' not in read('apps/mobile/src/humanPresence.ts'):raise RuntimeError(f'baseline reproduction drifted: {baseline}')
    patch_authority();patch_native_store();patch_calibration();patch_campaign();patch_versions_and_assets()
    out={'schema':'Dev2017PhysicalNoGoReproductionV1','release':'dev-20.18','baseline_release':'dev-20.17','baseline_sha':'84dae8257079cf4b83d9f34493a2aeb052b9ece3','source_defects_reproduced':baseline,'physical_observation':{'coordinator_calibration_generation':6,'peer_calibration_generations':[1,1],'peer_states':['STALE_AUTHORITY','STALE_AUTHORITY'],'coordinator_peer_ack_count':1,'distributed_calibration_ready':False,'stale_runstart_generation':8,'stale_runstart_calibration_generation':1,'local_ready':[None,None,None],'ready_count':[2,2,2],'artifact_transfer_failed':0,'critical_control_failure_count':0,'wire_oversize_block_count':0},'pass':all(baseline.values()),'screenshots_required':False}
    write('validation/reports/dev20_17_physical_no_go_reproduction.json',json.dumps(out,indent=2,sort_keys=True)+'\n')
    print('DEV20_18_PATCH_APPLIED')
if __name__=='__main__':main()
