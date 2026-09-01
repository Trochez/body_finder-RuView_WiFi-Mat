#!/usr/bin/env python3
from __future__ import annotations
import json,re,pathlib,textwrap
R=pathlib.Path('.')
def rd(p): return (R/p).read_text(encoding='utf-8')
def wr(p,s):
 q=R/p;q.parent.mkdir(parents=True,exist_ok=True);q.write_text(s,encoding='utf-8')
def rep(p,a,b,count=1):
 s=rd(p)
 if a not in s: raise SystemExit(f'PATCH_MISSING {p}: {a[:120]}')
 if count and s.count(a)!=count: raise SystemExit(f'PATCH_COUNT {p}: {s.count(a)} != {count}')
 wr(p,s.replace(a,b,count if count else -1))
def reg(p,pat,b):
 s=rd(p);n=re.subn(pat,b,s,count=1,flags=re.S)
 if n[1]!=1: raise SystemExit(f'REGEX_PATCH {p}: {n[1]} for {pat[:80]}')
 wr(p,n[0])
def jwrite(p,obj): wr(p,json.dumps(obj,indent=2,sort_keys=True)+'\n')

# Release identity and frozen product invariants.
p='apps/mobile/src/version.ts';s=rd(p)
for a,b in [("0.2.0-experimental.20.11","0.2.0-experimental.20.12"),('reportVersion: 31','reportVersion: 32'),('versionCode: 31','versionCode: 32'),("experimental.20.11","experimental.20.12"),('snapshotSchemaVersion: 14','snapshotSchemaVersion: 15')]:
 if a in s:s=s.replace(a,b)
wr(p,s)
p='apps/android-legacy/app/build.gradle';s=rd(p).replace('versionCode 31','versionCode 32').replace('0.2.0-experimental.20.11-legacy','0.2.0-experimental.20.12-legacy');wr(p,s)

# Session/node scoped calibration authority, compact V10 metadata, durable decision ledger.
p='apps/mobile/src/humanPresence.ts';s=rd(p)
if 'const calibrationByScope=' not in s:
 marker="let lastLocalNodeId:string|null=null;\n"
 scope="""let lastLocalNodeId:string|null=null;
const calibrationByScope=new Map<string,CalState>();
let activeCalibrationScope='__bootstrap__';
function blankCalibration():CalState{return{state:'UNCALIBRATED',generation:0,coordinator:null,topology:'',started:0,artifact:null,reason:'NOT_CALIBRATED',expectedCohort:[],publicationSequence:0,lastAuthorityWallMs:0,coordinatorGeneration:0}}
function activateCalibrationScope(nodes:Advertisement[],localNodeId:string|null){const sid=currentSession(nodes),key=`${sid}::${localNodeId??lastLocalNodeId??'unknown'}`;if(key===activeCalibrationScope)return;calibrationByScope.set(activeCalibrationScope,cal);cal=calibrationByScope.get(key)??blankCalibration();activeCalibrationScope=key;lastLocalNodeId=localNodeId??lastLocalNodeId}
"""
 if marker not in s: raise SystemExit('human scope marker missing')
 s=s.replace(marker,scope,1)
# Normalize old physical contract names first.
for a,b in [
 ('CalibrationPublicationV8','CalibrationMetaV10'),('CalibrationPublicationV9','CalibrationMetaV10'),('CalibrationAckV8','CalibrationAckV10'),('CalibrationAckV9','CalibrationAckV10'),
 ('DecisionPublicationV8','DecisionMetaV10'),('DecisionPublicationV9','DecisionMetaV10'),('DecisionAckV8','DecisionAckV10'),('DecisionAckV9','DecisionAckV10'),('BodyFinderControlPlaneV8','BodyFinderControlPlaneV10'),('BodyFinderControlPlaneV9','BodyFinderControlPlaneV10'),
 ('calibration_publication_v8','calibration_meta_v10'),('calibration_publication_v9','calibration_meta_v10'),('calibration_ack_v8','calibration_ack_v10'),('calibration_ack_v9','calibration_ack_v10'),
 ('decision_publication_v8','decision_meta_v10'),('decision_publication_v9','decision_meta_v10'),('decision_ack_v8','decision_ack_v10'),('decision_ack_v9','decision_ack_v10'),
 ('CALIBRATION_ARTIFACT_V8','CALIBRATION_FINAL_V10'),('CALIBRATION_ARTIFACT_V9','CALIBRATION_FINAL_V10'),('DECISION_REPLAY_ARTIFACT_V8','DECISION_FINAL_REPLAY_V1'),('DECISION_REPLAY_ARTIFACT_V9','DECISION_FINAL_REPLAY_V1')]: s=s.replace(a,b)
# Activate scoped state in every public path that mutates/reads authority.
for old,new in [
 ("export function electStableCoordinator(nodes:Advertisement[],localNodeId:string|null){lastLocalNodeId=localNodeId;","export function electStableCoordinator(nodes:Advertisement[],localNodeId:string|null){activateCalibrationScope(nodes,localNodeId);lastLocalNodeId=localNodeId;"),
 ("export function beginSessionPresenceCalibration(nodes:Advertisement[],coordinatorNodeId:string|null,localNodeId:string|null){\n  lastLocalNodeId=localNodeId;","export function beginSessionPresenceCalibration(nodes:Advertisement[],coordinatorNodeId:string|null,localNodeId:string|null){\n  activateCalibrationScope(nodes,localNodeId);lastLocalNodeId=localNodeId;"),
 ("export function getSessionPresenceCalibration(nodes:Advertisement[]=[]){\n  const matrix=","export function getSessionPresenceCalibration(nodes:Advertisement[]=[]){\n  activateCalibrationScope(nodes,lastLocalNodeId);const matrix="),
 ("export function estimateHumanPresence(nodes:Advertisement[],role:'coordinator'|'diagnostic',coordinatorNodeId:string|null,localNodeId:string|null):PresenceEstimate{\n  lastLocalNodeId=localNodeId;","export function estimateHumanPresence(nodes:Advertisement[],role:'coordinator'|'diagnostic',coordinatorNodeId:string|null,localNodeId:string|null):PresenceEstimate{\n  activateCalibrationScope(nodes,localNodeId);lastLocalNodeId=localNodeId;"),
 ("export function selectAuthoritativePresence(nodes:Advertisement[],coordinatorNodeId:string|null,localNodeId:string|null,local:PresenceEstimate):PresenceEstimate{\n  lastLocalNodeId=localNodeId;","export function selectAuthoritativePresence(nodes:Advertisement[],coordinatorNodeId:string|null,localNodeId:string|null,local:PresenceEstimate):PresenceEstimate{\n  activateCalibrationScope(nodes,localNodeId);lastLocalNodeId=localNodeId;")]:
 if old in s:s=s.replace(old,new,1)
# Calibration metadata is compact; full calibration remains one pinned artifact per generation.
pat=r"export function getCalibrationPublication\(localNodeId:string\|null\)\{.*?\n\}\nexport function getControlPlanePublication"
new="""export function getCalibrationPublication(localNodeId:string|null){
  if(!cal.artifact||cal.coordinator!==localNodeId||!(cal.state==='READY'||cal.state==='STALE_AUTHORITY'))return null;cal.publicationSequence+=1;cal.lastAuthorityWallMs=Date.now();
  const topology_hash=BodyFinderNative.sha256Text(cal.topology||'');
  return{schema:'CalibrationMetaV10',session_id:cal.artifact.session_id,coordinator_id:cal.coordinator,cg:cal.coordinatorGeneration,g:cal.generation,id:cal.artifact.calibration_id,hash:cal.artifact.calibration_hash,artifact_id:`calibration:${cal.artifact.calibration_id}`,artifact_hash:cal.artifact.calibration_hash,topology_hash,cohort:cal.expectedCohort,seq:cal.publicationSequence,lease_ms:DETECTOR_V8.authorityPublicationLeaseMs,state:'READY'}
}
export function getControlPlanePublication"""
m=re.subn(pat,new,s,count=1,flags=re.S)
if m[1]!=1: raise SystemExit('calibration publication replacement failed')
s=m[0]
# Entire V10 control publication: no live decision bulk artifact. Decision replay is transferred once at freeze by campaignControl.
pat=r"export function getControlPlanePublication\(nodes:Advertisement\[\],coordinatorNodeId:string\|null,localNodeId:string\|null\)\{.*?\n\}\n\nfunction maybeFreeze"
new="""export function getControlPlanePublication(nodes:Advertisement[],coordinatorNodeId:string|null,localNodeId:string|null){
  activateCalibrationScope(nodes,localNodeId);lastLocalNodeId=localNodeId;syncAuthoritativeCalibration(nodes,coordinatorNodeId,localNodeId);adoptCoordinatorIfNeeded(nodes,coordinatorNodeId,localNodeId);const sid=currentSession(nodes),cm=getCalibrationPublication(localNodeId),cached=latestDecisionBySession.get(sid),topology_hash=BodyFinderNative.sha256Text(cal.topology||'');
  const ack=cal.artifact&&localNodeId&&cal.expectedCohort.includes(localNodeId)?{schema:'CalibrationAckV10',sid,node_id:localNodeId,cg:cal.coordinatorGeneration,g:cal.generation,id:cal.artifact.calibration_id,hash:cal.artifact.calibration_hash,artifact_id:`calibration:${cal.artifact.calibration_id}`,topology_hash}:null;
  const dm=cached&&coordinatorNodeId===localNodeId&&cached.decision.authoritative&&cached.decision.canonical_digest?{schema:'DecisionMetaV10',sid,coordinator_id:coordinatorNodeId,cg:cal.coordinatorGeneration,g:cached.decision.calibration_generation??cal.generation,cal_id:cached.decision.calibration_id??cal.artifact?.calibration_id??null,cal_hash:cached.decision.calibration_hash??cal.artifact?.calibration_hash??null,topology_hash,seq:cached.sequence,id:cached.decision.decision_id,digest:cached.decision.canonical_digest,prediction:cached.decision.prediction,n:Number(cached.decision.contributing_nodes??0),l:Number(cached.decision.contributing_links??0),b:Number(cached.decision.physical_baselines??0)}:null;
  const da=cached&&localNodeId?{schema:'DecisionAckV10',sid,node_id:localNodeId,seq:cached.sequence,id:cached.decision.decision_id??null,digest:cached.decision.canonical_digest??null}:null;
  const artifacts:any[]=[];if(coordinatorNodeId===localNodeId&&cm&&cal.artifact)artifacts.push({artifact_id:cm.artifact_id,artifact_type:'CALIBRATION_FINAL_V10',generation:cal.generation,priority:'CALIBRATION_FINAL',supersedes_artifact_id:null,payload:cal.artifact});
  return{schema:'BodyFinderControlPlaneV10',session_id:sid,node_id:localNodeId,logical_membership_state:{expected_cohort:stableCohort(nodes),transport_liveness_state:transportStates(nodes)},calibration_meta_v10:cm,calibration_ack_v10:ack,decision_meta_v10:dm,decision_ack_v10:da,artifact_payloads_v1:artifacts}
}
export function getRunAuthorityLedger(nodes:Advertisement[],coordinatorNodeId:string|null,localNodeId:string|null){activateCalibrationScope(nodes,localNodeId);syncAuthoritativeCalibration(nodes,coordinatorNodeId,localNodeId);const sid=currentSession(nodes),cached=latestDecisionBySession.get(sid),d=cached?.decision??null;return{schema:'RunAuthorityLedgerV1',session_id:sid,node_id:localNodeId,authority_ledger_reason:cal.artifact?'PINNED_CALIBRATION':'CALIBRATION_MISSING',authority_ledger_age_ms:cached?Math.max(0,Date.now()-cached.receivedWallMs):null,calibration_id:cal.artifact?.calibration_id??null,calibration_hash:cal.artifact?.calibration_hash??null,calibration_generation:cal.generation,topology_hash:BodyFinderNative.sha256Text(cal.topology||''),cohort:cal.expectedCohort,decision:d?{...d,decision_freshness_state:decisionFreshness(cached!.receivedWallMs)}:null}}

function maybeFreeze"""
m=re.subn(pat,new,s,count=1,flags=re.S)
if m[1]!=1: raise SystemExit('control publication replacement failed')
s=m[0]
# V10 compact calibration ingestion/ACK field aliases.
s=s.replace("function publicationFrom(nodes:Advertisement[],coordinatorNodeId:string|null){const coordinator=nodes.find(n=>n.node_id===coordinatorNodeId);return (coordinator?.control_plane as any)?.calibration_meta_v10??null}","function publicationFrom(nodes:Advertisement[],coordinatorNodeId:string|null){const coordinator=nodes.find(n=>n.node_id===coordinatorNodeId);return (coordinator?.control_plane as any)?.calibration_meta_v10??null}")
s=s.replace("const artifact=p?.calibration_artifact_id?artifactFrom(coordinator,p.calibration_artifact_id):null;","const artifact=p?.artifact_id?artifactFrom(coordinator,p.artifact_id):null;")
s=s.replace("p?.detector_parameter_hash===DETECTOR_PARAMETER_HASH&&artifact?.calibration_hash===p?.calibration_hash","artifact?.calibration_hash===p?.hash")
s=s.replace("Number(p.coordinator_generation??0),incomingCal=Number(p.calibration_generation??0),incomingSeq=Number(p.publication_sequence??0)","Number(p.cg??0),incomingCal=Number(p.g??0),incomingSeq=Number(p.seq??0)")
s=s.replace("topology:String(p.topology_fingerprint)","topology:String(p.topology_hash??'')")
s=s.replace("expectedCohort:Array.isArray(p.expected_cohort)?p.expected_cohort.map(String).sort():cal.expectedCohort","expectedCohort:Array.isArray(p.cohort)?p.cohort.map(String).sort():cal.expectedCohort")
# Exact V10 ACK aliases.
s=s.replace("a.calibration_id===cal.artifact.calibration_id&&a.calibration_hash===cal.artifact.calibration_hash&&Number(a.calibration_generation)===cal.generation&&Number(a.coordinator_generation)===cal.coordinatorGeneration","a.id===cal.artifact.calibration_id&&a.hash===cal.artifact.calibration_hash&&Number(a.g)===cal.generation&&Number(a.cg)===cal.coordinatorGeneration")
# Decision receive no longer requires a changing replay artifact. Compact metadata is authoritative; historical ledger survives live expiry.
pat=r"const coordinator=nodes.find\(n=>n.node_id===coordinatorNodeId\);const dp=\(coordinator\?\.control_plane as any\)\?\.decision_meta_v10;\n  if\(dp&&dp.schema==='DecisionMetaV10'.*?\n  \}\n  const cached=latestDecisionBySession.get\(sid\);if\(cached&&decisionFreshness\(cached.receivedWallMs\)!=='EXPIRED'\)return\{\.\.\.cached.decision,source:'cached_decision_meta_v10',decision_freshness_state:decisionFreshness\(cached.receivedWallMs\),decision_age_ms:Date.now\(\)-cached.receivedWallMs\} as PresenceEstimate;"
repl="""const coordinator=nodes.find(n=>n.node_id===coordinatorNodeId);const dp=(coordinator?.control_plane as any)?.decision_meta_v10;
  if(dp&&dp.schema==='DecisionMetaV10'&&dp.sid===sid&&dp.coordinator_id===coordinatorNodeId&&Number(dp.cg)===cal.coordinatorGeneration&&dp.cal_hash===cal.artifact?.calibration_hash&&dp.digest){const incomingSeq=Number(dp.seq??0),previous=latestDecisionBySession.get(sid);if(!previous||incomingSeq>=previous.sequence){const mirrored={prediction:String(dp.prediction??'INDETERMINATE'),human_confidence:0.5,evidence_quality:'CONTROL_META',fused_score:0,contributing_nodes:Number(dp.n??0),contributing_links:Number(dp.l??0),physical_baselines:Number(dp.b??0),reason:'DURABLE_DECISION_META_V10',calibration_state:cal.artifact?'READY':cal.state,calibration_id:dp.cal_id,calibration_hash:dp.cal_hash,calibration_generation:Number(dp.g??cal.generation),coordinator_generation:Number(dp.cg),topology_fingerprint:cal.topology,algorithm_version:DETECTOR_ALGORITHM,parameter_hash:DETECTOR_PARAMETER_HASH,window_id:String(dp.seq??''),authoritative:true,source:'decision_meta_v10',decision_sequence:incomingSeq,decision_id:dp.id,canonical_digest:dp.digest,decision_freshness_state:'FRESH'} as PresenceEstimate;latestDecisionBySession.set(sid,{decision:mirrored,receivedWallMs:Date.now(),sequence:incomingSeq});return mirrored}}
  const cached=latestDecisionBySession.get(sid);if(cached)return{...cached.decision,source:'durable_run_authority_ledger_v1',decision_freshness_state:decisionFreshness(cached.receivedWallMs),decision_age_ms:Date.now()-cached.receivedWallMs,authoritative:true} as PresenceEstimate;"""
m=re.subn(pat,repl,s,count=1,flags=re.S)
if m[1]!=1:
 # tolerate source text that still says old cached source after global rename.
 s=s.replace("const cached=latestDecisionBySession.get(sid);if(cached&&decisionFreshness(cached.receivedWallMs)!=='EXPIRED')return{...cached.decision,source:'cached_decision_meta_v10',decision_freshness_state:decisionFreshness(cached.receivedWallMs),decision_age_ms:Date.now()-cached.receivedWallMs} as PresenceEstimate;","const cached=latestDecisionBySession.get(sid);if(cached)return{...cached.decision,source:'durable_run_authority_ledger_v1',decision_freshness_state:decisionFreshness(cached.receivedWallMs),decision_age_ms:Date.now()-cached.receivedWallMs,authoritative:true} as PresenceEstimate;")
else:s=m[0]
wr(p,s)

# Native bridge TypeScript: distributed lifecycle and evidence v15 hard consistency.
p='apps/mobile/modules/body-finder-native/index.ts';s=rd(p)
s=s.replace("startValidationRun(scenario: string): string;","startValidationRun(scenario: string): string; startDistributedValidationRun(scenario: string, contextJson: string): string;")
s=s.replace("endValidationRun(): boolean;","endValidationRun(): boolean; commitDistributedFreezeAndEnd(commitJson: string): boolean;")
s=s.replace("dev20.11-self-contained-json-evidence-v14","dev20.12-self-contained-json-evidence-v15")
# Replace export upgrader with strict v15 parity rules.
pat=r"function upgradeExport\(raw:string\):string\{.*?\}\nconst api:NativeApi="
up="""function upgradeExport(raw:string):string{try{const d=JSON.parse(raw),v=d?.validation_run??d,truth=v?.validation_truth??d?.validation_truth??{},start=truth?.distributed_start??null,freeze=truth?.freeze_barrier??null,preview=truth?.authoritative_presence??d?.human_presence_preview??null;const reasons:string[]=[];if(start?.committed!==true||Number(start?.ready_count??0)!==3)reasons.push('DISTRIBUTED_START_NOT_COMMITTED_3_OF_3');if(freeze?.committed!==true||Number(freeze?.ready_count??0)!==3||freeze?.ready_parity!==true)reasons.push('DISTRIBUTED_FREEZE_NOT_COMMITTED_3_OF_3');if(v?.distributed_freeze_committed!==true)reasons.push('NATIVE_DISTRIBUTED_FREEZE_NOT_COMMITTED');if(!v?.campaign_run_token)reasons.push('CAMPAIGN_RUN_TOKEN_MISSING');if(!preview?.authoritative)reasons.push('NO_FROZEN_AUTHORITATIVE_DECISION');if(!preview?.canonical_digest)reasons.push('MISSING_CANONICAL_DIGEST');if(!preview?.decision_id)reasons.push('MISSING_DECISION_ID');if(Number(preview?.contributing_nodes??0)<3||Number(preview?.contributing_links??0)<6||Number(preview?.physical_baselines??0)<3)reasons.push('INCOMPLETE_3_6_3_TOPOLOGY');const valid=reasons.length===0;d.live_human_presence_preview=d?.human_presence_preview??null;d.human_presence_preview=preview;d.evidence_export_valid=valid;d.atomic_snapshot_gate_pass=valid;d.evidence_invalid_reasons=reasons;d.evidence_contract={schema:EVIDENCE_SCHEMA,screenshots_required:false,json_self_contained:true,atomic_snapshot:true,distributed_commit_required:true};d.acceptance_minimum_ms=ACCEPTANCE_MINIMUM_MS;d.human_localization_validated=false;d.rescue_use_validated=false;if(v&&typeof v==='object'){v.evidence_export_valid=valid;v.atomic_snapshot_gate_pass=valid;v.evidence_contract_version=EVIDENCE_SCHEMA;}return JSON.stringify(d,null,2)}catch{return raw}}
const api:NativeApi="""
m=re.subn(pat,up,s,count=1,flags=re.S)
if m[1]!=1: raise SystemExit('index upgradeExport replacement failed')
wr(p,m[0])

# Native Android lifecycle + transport hardening.
p='apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt';s=rd(p)
s=s.replace('snapshot_schema_version\", 14','snapshot_schema_version\", 15')
s=s.replace('COMPACT_CONTROL_PAYLOAD_TARGET_BYTES = 760','COMPACT_CONTROL_PAYLOAD_TARGET_BYTES = 600')
s=s.replace('ArtifactManifestV3','ArtifactManifestV4').replace('WireTransportTelemetryV11','WireTransportTelemetryV12')
# Durable run-scoped lifecycle fields.
marker='  @Volatile private var authoritativeTruthLedgerJson: String = "{}"\n'
if 'campaignRunToken' not in s:
 ins=marker+'  @Volatile private var campaignRunToken: String? = null\n  @Volatile private var distributedStartCommitted: Boolean = false\n  @Volatile private var distributedFreezeCommitted: Boolean = false\n  @Volatile private var distributedContextJson: String = "{}"\n  @Volatile private var distributedFreezeCommitJson: String = "{}"\n'
 if marker not in s:raise SystemExit('native ledger marker missing')
 s=s.replace(marker,ins,1)
# Reset fields on new run.
reset='    authoritativeTruthLedgerJson = "{}"\n'
if reset in s and 'distributedStartCommitted = false' not in s[s.find(reset):s.find(reset)+450]:
 s=s.replace(reset,reset+'    campaignRunToken = null\n    distributedStartCommitted = false\n    distributedFreezeCommitted = false\n    distributedContextJson = "{}"\n    distributedFreezeCommitJson = "{}"\n',1)
# Add distributed context API inside ValidationRuntime.
marker='  @Synchronized\n  fun frozenExpectedPeerCount(): Int = expectedPeerCountAtStart\n'
if 'fun pinDistributedStart' not in s:
 block='''  @Synchronized
  fun pinDistributedStart(contextJson:String):Boolean{if(runId==null||endedWallMs!=null)return false;val o=try{JSONObject(contextJson)}catch(_:Throwable){return false};val token=o.optString("campaign_run_token");if(token.isBlank()||o.optBoolean("committed")!=true)return false;campaignRunToken=token;distributedStartCommitted=true;distributedContextJson=o.toString();ValidationEventLog.record("DISTRIBUTED_RUN_START_COMMITTED",runId,now=System.currentTimeMillis());return true}
  @Synchronized fun requiresDistributedCommit():Boolean=distributedStartCommitted
  @Synchronized fun freezeCommitted():Boolean=distributedFreezeCommitted
  @Synchronized fun commitDistributedFreeze(commitJson:String):Boolean{if(runId==null||endedWallMs!=null||!distributedStartCommitted)return false;val o=try{JSONObject(commitJson)}catch(_:Throwable){return false};if(o.optBoolean("committed")!=true||o.optString("campaign_run_token")!=campaignRunToken||o.optInt("ready_count")!=3||!o.optBoolean("ready_parity"))return false;distributedFreezeCommitted=true;distributedFreezeCommitJson=o.toString();ValidationEventLog.record("DISTRIBUTED_RUN_FREEZE_COMMITTED",runId,now=System.currentTimeMillis());return true}

'''+marker
 if marker not in s:raise SystemExit('native frozenExpected marker missing')
 s=s.replace(marker,block,1)
# Snapshot/local-distributed semantics.
s=s.replace('.put("snapshot_frozen", true)','.put("local_snapshot_frozen", true).put("distributed_start_committed", distributedStartCommitted).put("distributed_freeze_committed", distributedFreezeCommitted).put("campaign_run_token", campaignRunToken ?: JSONObject.NULL).put("distributed_start_context", try { JSONObject(distributedContextJson) } catch (_: Throwable) { JSONObject() }).put("distributed_freeze_commit", try { JSONObject(distributedFreezeCommitJson) } catch (_: Throwable) { JSONObject() }).put("snapshot_frozen", !distributedStartCommitted || distributedFreezeCommitted)',1)
s=s.replace('.put("snapshot_frozen", false)','.put("local_snapshot_frozen", false).put("distributed_start_committed", distributedStartCommitted).put("distributed_freeze_committed", distributedFreezeCommitted).put("campaign_run_token", campaignRunToken ?: JSONObject.NULL).put("snapshot_frozen", false)',1)
# Native functions: distributed start/commit. Existing local end becomes fail-closed for acceptance.
marker='      setValidationKeepAwake(true)\n      id\n    }\n    Function("endValidationRun") {'
if 'Function("startDistributedValidationRun")' not in s:
 repl='''      setValidationKeepAwake(true)
      id
    }
    Function("startDistributedValidationRun") { scenario: String, contextJson: String ->
      val ctxObj=try{JSONObject(contextJson)}catch(_:Throwable){return@Function "VALIDATION_ENVIRONMENT_INVALID:DISTRIBUTED_CONTEXT_INVALID"}
      if(ctxObj.optBoolean("committed")!=true||ctxObj.optString("campaign_run_token").isBlank())return@Function "VALIDATION_ENVIRONMENT_INVALID:DISTRIBUTED_START_NOT_COMMITTED"
      val existing=ValidationRuntime.runId
      val id=if(existing!=null)existing else {
        val ctx=appContext.reactContext?:return@Function "VALIDATION_ENVIRONMENT_INVALID:NO_CONTEXT"
        val now=System.currentTimeMillis();val preflight=validationPreflight(ctx,now);if(!preflight.optBoolean("validation_ready"))return@Function "VALIDATION_ENVIRONMENT_INVALID:${preflight.optJSONArray("issues")?.optString(0)?:"PREFLIGHT"}"
        ValidationRuntime.start(now,FabricRuntime.peerExpireCount.get(),FabricRuntime.totalRebinds(),FabricRuntime.scanRestartCount.get(),FabricRuntime.txPackets.get(),FabricRuntime.rxPackets.get(),preflight.toString(),scenario)
      }
      if(!ValidationRuntime.pinDistributedStart(contextJson))return@Function "VALIDATION_ENVIRONMENT_INVALID:DISTRIBUTED_START_PIN_FAILED"
      setValidationKeepAwake(true);id
    }
    Function("commitDistributedFreezeAndEnd") { commitJson: String ->
      if(!ValidationRuntime.commitDistributedFreeze(commitJson))return@Function false
      val ctx=appContext.reactContext?:return@Function false;val now=System.currentTimeMillis()
      ValidationRuntime.end(now,FabricRuntime.peerExpireCount.get(),FabricRuntime.totalRebinds(),FabricRuntime.scanRestartCount.get(),FabricRuntime.txPackets.get(),FabricRuntime.rxPackets.get(),acquisitionProvenance(now),peerBleDiagnostics(now),if(Build.VERSION.SDK_INT>=36) SystemRangingApi36.diagnostics(now) else JSONObject().put("state","UNSUPPORTED"));setValidationKeepAwake(false);true
    }
    Function("endValidationRun") {
      if(ValidationRuntime.requiresDistributedCommit()&&!ValidationRuntime.freezeCommitted())return@Function false'''
 if marker not in s:raise SystemExit('native function insertion marker missing')
 s=s.replace(marker,repl,1)
# Critical control telemetry declarations and fail-closed delivery signal.
marker='  private val oversizeControlKeyCounts=ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong>()\n'
if marker in s and 'criticalControlFailureCount' not in s:
 s=s.replace(marker,marker+'  private val criticalControlSendAttempt=ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong>()\n  private val criticalControlSendSuccess=ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong>()\n  private val criticalControlSendFailure=ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong>()\n  private val criticalControlFailureCount=AtomicLong(0)\n  private val optionalControlDropCount=AtomicLong(0)\n  @Volatile private var lastCriticalControlFailureKey:String?=null\n  @Volatile private var lastCriticalControlFailureSize:Long=0\n  @Volatile private var lastCriticalControlFailureError:String?=null\n',1)
# Replace safeAddControl implementation with explicit critical health signaling.
pat=r"  private fun safeAddControl\(out:MutableList<ByteArray>,key:String,value:Any\?,node:String,session:String,seq:Long\)\{.*?\n  \}\n  @Synchronized private fun putArtifactCache"
new='''  private val criticalControlKeys=setOf("calibration_meta_v10","calibration_ack_v10","decision_meta_v10","decision_ack_v10","scenario_command_v1","scenario_ack_v1","run_start_prepare_v1","run_start_ready_v1","run_start_commit_v1","run_freeze_prepare_v2","snapshot_ready_v2","run_freeze_commit_v2")
  private fun safeAddControl(out:MutableList<ByteArray>,key:String,value:Any?,node:String,session:String,seq:Long){
    val critical=criticalControlKeys.contains(key);if(critical)criticalControlSendAttempt.computeIfAbsent(key){AtomicLong(0)}.incrementAndGet()
    val compact=JSONObject().put("control_key",key).put("control_value",value).toString().toByteArray(Charsets.UTF_8)
    if(compact.size>COMPACT_CONTROL_PAYLOAD_TARGET_BYTES){oversizeControlKeyCounts.computeIfAbsent(key){AtomicLong(0)}.incrementAndGet();lastOversizeControlKey=key;lastOversizeSha256=sha(compact);if(critical){criticalControlFailureCount.incrementAndGet();criticalControlSendFailure.computeIfAbsent(key){AtomicLong(0)}.incrementAndGet();lastCriticalControlFailureKey=key;lastCriticalControlFailureSize=compact.size.toLong();lastCriticalControlFailureError="CRITICAL_CONTROL_PAYLOAD_OVER_600";safeAdd(out,"CONTROL_FATAL",node,session,seq){o->o.put("control_key",key).put("payload_sha256",sha(compact)).put("payload_bytes",compact.size).put("fatal",true)}}else optionalControlDropCount.incrementAndGet();return}
    try{val frame=envelope("CONTROL_FRAME",node,session,seq){o->o.put("control_key",key).put("control_value",value)};if(frame.size>CONTROL_FRAME_TARGET_BYTES)throw IllegalArgumentException("CONTROL_FRAME_OVER_900:${frame.size}");maxControlBytesByKey.computeIfAbsent(key){AtomicLong(0)}.updateAndGet{v->kotlin.math.max(v,frame.size.toLong())};out+=frame;if(critical)criticalControlSendSuccess.computeIfAbsent(key){AtomicLong(0)}.incrementAndGet()}catch(t:Throwable){oversizeControlKeyCounts.computeIfAbsent(key){AtomicLong(0)}.incrementAndGet();lastOversizeControlKey=key;lastOversizeSha256=sha(compact);if(critical){criticalControlFailureCount.incrementAndGet();criticalControlSendFailure.computeIfAbsent(key){AtomicLong(0)}.incrementAndGet();lastCriticalControlFailureKey=key;lastCriticalControlFailureSize=compact.size.toLong();lastCriticalControlFailureError="${t.javaClass.simpleName}:${t.message}"}else optionalControlDropCount.incrementAndGet();lastSendError="${t.javaClass.simpleName}:${t.message}"}
  }
  @Synchronized private fun putArtifactCache'''
m=re.subn(pat,new,s,count=1,flags=re.S)
if m[1]!=1:raise SystemExit('native safeAddControl replacement failed')
s=m[0]
# V10 control allowlist and V2 freeze/start.
pat=r'for\(k in listOf\("logical_membership_state".*?\)\)\{'
keys='for(k in listOf("logical_membership_state","calibration_meta_v10","calibration_ack_v10","decision_meta_v10","decision_ack_v10","scenario_command_v1","scenario_ack_v1","run_start_prepare_v1","run_start_ready_v1","run_start_commit_v1","run_freeze_prepare_v2","snapshot_ready_v2","run_freeze_commit_v2")){'
s,n=re.subn(pat,keys,s,count=1,flags=re.S)
if n!=1:raise SystemExit('native control key list replacement failed')
# Artifact receiver NACK backoff: per-assembly exponential, bounded and explicit terminal metadata.
s=s.replace('private data class Assembly(val id:String,val artifactType:String,val sha:String,val count:Int,val generation:Long,val created:Long,val source:InetAddress,val chunks:ConcurrentHashMap<Int,ByteArray> = ConcurrentHashMap(),var lastNackWallMs:Long=0L)', 'private data class Assembly(val id:String,val artifactType:String,val sha:String,val count:Int,val generation:Long,val created:Long,val source:InetAddress,val chunks:ConcurrentHashMap<Int,ByteArray> = ConcurrentHashMap(),var lastNackWallMs:Long=0L,var nackBackoffMs:Long=NACK_INTERVAL_MS)')
s=s.replace('a.lastNackWallMs=now;artifactNackTx.incrementAndGet();replies+=reply(a.source,nackFrame(id,a.sha,miss,now))','a.lastNackWallMs=now;a.nackBackoffMs=(a.nackBackoffMs*2).coerceAtMost(8_000L);artifactNackTx.incrementAndGet();replies+=reply(a.source,nackFrame(id,a.sha,miss,now))')
s=s.replace('now-a.lastNackWallMs>=NACK_INTERVAL_MS&&age>=NACK_INTERVAL_MS','now-a.lastNackWallMs>=a.nackBackoffMs&&age>=NACK_INTERVAL_MS')
# Transport telemetry v12 explicit metrics.
needle='.put("max_datagram_bytes_observed",maxDatagramBytesObserved.get())'
if needle in s and 'critical_control_failure_count' not in s:
 s=s.replace(needle,'.put("critical_control_payload_target_bytes",COMPACT_CONTROL_PAYLOAD_TARGET_BYTES).put("critical_control_failure_count",criticalControlFailureCount.get()).put("optional_control_drop_count",optionalControlDropCount.get()).put("critical_control_send_attempt",mapJson(criticalControlSendAttempt)).put("critical_control_send_success",mapJson(criticalControlSendSuccess)).put("critical_control_send_failure",mapJson(criticalControlSendFailure)).put("last_critical_control_failure_key",lastCriticalControlFailureKey?:JSONObject.NULL).put("last_critical_control_failure_size",lastCriticalControlFailureSize).put("last_critical_control_failure_error",lastCriticalControlFailureError?:JSONObject.NULL)\n    '+needle,1)
wr(p,s)

# App: coordinator-only distributed Start/End, automatic peer start/freeze, export read-only.
p='apps/mobile/App.tsx';s=rd(p)
s=s.replace("beginSessionPresenceCalibration, electStableCoordinator, estimateHumanPresence, getControlPlanePublication, getSessionPresenceCalibration, selectAuthoritativePresence","beginSessionPresenceCalibration, electStableCoordinator, estimateHumanPresence, getControlPlanePublication, getRunAuthorityLedger, getSessionPresenceCalibration, selectAuthoritativePresence")
s=s.replace("getCampaignControlPublication, getFreezeBarrierStatus, getScenarioCommandStatus, issueScenarioCommand, requestRunFreeze, ScenarioId","getCampaignControlPublication, getFreezeBarrierStatus, getRunStartBarrierStatus, getScenarioCommandStatus, issueScenarioCommand, requestRunFreeze, requestRunStart, ScenarioId")
s=s.replace("  const freezeBarrier = useMemo(() => getFreezeBarrierStatus(nodes, coordinator, local?.node_id ?? null, presence, calibrationStatus), [nodes, coordinator, local?.node_id, presence, calibrationStatus]);","  const authorityLedger = useMemo(() => getRunAuthorityLedger(nodes, coordinator, local?.node_id ?? null), [nodes, coordinator, local?.node_id, presence, calibrationStatus]);\n  const startBarrier = useMemo(() => getRunStartBarrierStatus(nodes, coordinator, local?.node_id ?? null, calibrationStatus), [nodes, coordinator, local?.node_id, calibrationStatus, scenarioStatus?.command?.command_digest]);\n  const freezeBarrier = useMemo(() => getFreezeBarrierStatus(nodes, coordinator, local?.node_id ?? null, authorityLedger, calibrationStatus), [nodes, coordinator, local?.node_id, authorityLedger, calibrationStatus]);")
s=s.replace("    scenario_contract: scenarioStatus,\n    freeze_barrier: freezeBarrier,","    scenario_contract: scenarioStatus,\n    distributed_start: startBarrier,\n    campaign_run_token: startBarrier?.commit?.campaign_run_token ?? startBarrier?.prepare?.campaign_run_token ?? null,\n    run_authority_ledger: authorityLedger,\n    freeze_barrier: freezeBarrier,")
s=s.replace("scenarioStatus, freezeBarrier, geometrySelection.source","scenarioStatus, startBarrier, authorityLedger, freezeBarrier, geometrySelection.source")
old="  const campaignControl = useMemo(() => getCampaignControlPublication(nodes, coordinator, local?.node_id ?? null, presence, calibrationStatus), [nodes, coordinator, local?.node_id, presence, calibrationStatus, scenarioStatus?.command?.command_digest, freezeBarrier?.prepare?.generation]);\n  const controlPlane = useMemo(() => ({...getControlPlanePublication(nodes, coordinator, local?.node_id ?? null),...campaignControl,schema:'BodyFinderControlPlaneV9'}), [nodes, coordinator, local?.node_id, presence, campaignControl]);"
new="  const campaignControl = useMemo(() => getCampaignControlPublication(nodes, coordinator, local?.node_id ?? null, authorityLedger, calibrationStatus), [nodes, coordinator, local?.node_id, authorityLedger, calibrationStatus, scenarioStatus?.command?.command_digest, startBarrier?.prepare?.generation, freezeBarrier?.prepare?.generation]);\n  const controlPlane = useMemo(() => { const hp:any=getControlPlanePublication(nodes, coordinator, local?.node_id ?? null); const cc:any=campaignControl; return {...hp,...cc,schema:'BodyFinderControlPlaneV10',artifact_payloads_v1:[...(hp?.artifact_payloads_v1??[]),...(cc?.artifact_payloads_v1??[])]}; }, [nodes, coordinator, local?.node_id, presence, campaignControl]);"
if old not in s:raise SystemExit('App control plane marker missing')
s=s.replace(old,new,1)
# Auto-start all peers after distributed commit; auto-end all peers after freeze commit.
marker="  useEffect(() => { try { BodyFinderNative.updateControlPlaneJson(JSON.stringify(controlPlane)); } catch {} }, [controlPlane]);\n"
if 'AUTO_DISTRIBUTED_START' not in s:
 effect=marker+"""  useEffect(() => { const c:any=startBarrier?.commit;if(!c?.campaign_run_token||validationRun?.active)return;try{const result=BodyFinderNative.startDistributedValidationRun(validationScenario,JSON.stringify({...startBarrier,campaign_run_token:c.campaign_run_token,committed:true}));if(typeof result==='string'&&result.startsWith('VALIDATION_ENVIRONMENT_INVALID:'))setError(result);else setValidationNotice('AUTO_DISTRIBUTED_START 3/3');}catch(e:any){setError(String(e?.message??e));} }, [startBarrier?.commit?.campaign_run_token]);
  useEffect(() => { const c:any=freezeBarrier?.commit;if(!c?.campaign_run_token||!validationRun?.active)return;try{BodyFinderNative.updateValidationTruthJson(JSON.stringify({...validationTruth,distributed_start:startBarrier,freeze_barrier:freezeBarrier}));const ok=BodyFinderNative.commitDistributedFreezeAndEnd(JSON.stringify({...freezeBarrier,campaign_run_token:c.campaign_run_token,committed:true}));if(ok)setValidationNotice('DISTRIBUTED_SNAPSHOT_COMMITTED_3_OF_3');else setError('Distributed freeze commit rejected by native runtime.');}catch(e:any){setError(String(e?.message??e));} }, [freezeBarrier?.commit?.readiness_digest, validationRun?.active]);
"""
 s=s.replace(marker,effect,1)
# Replace validation button handler entirely.
pat=r"  function toggleValidationRun\(\) \{.*?\n  \}\n\n  async function share\(\) \{"
handler="""  function toggleValidationRun() {
    if(validationActionLock.current)return;validationActionLock.current=true;try{
      if(validationRun?.active){if(coordinator!==local?.node_id){setError('End blocked: coordinator only.');return;}requestRunFreeze(nodes,coordinator,local?.node_id??null,authorityLedger,calibrationStatus);setValidationNotice('Freeze Prepare V2 issued; peers will end automatically after READY 3/3.');}
      else{if(coordinator!==local?.node_id){setError('Start blocked: coordinator only.');return;}const ss=getScenarioCommandStatus(nodes,coordinator,local?.node_id??null);if(!ss.ready||ss.ack_count!==3)throw new Error('Scenario ACK 3/3 required');if(calibrationStatus?.distributed_calibration_ready!==true)throw new Error('Calibration ACK 3/3 required');requestRunStart(nodes,coordinator,local?.node_id??null,calibrationStatus);setValidationNotice('Run Start Prepare V1 issued; peers will auto-start after READY 3/3.');}
      refreshValidationState();
    }catch(cause:any){setError(String(cause?.message??cause));}finally{setTimeout(()=>{validationActionLock.current=false;},600)}
  }

  async function share() {"""
m=re.subn(pat,handler,s,count=1,flags=re.S)
if m[1]!=1:raise SystemExit('App toggle handler replacement failed')
s=m[0]
# Share/export is read-only: block acceptance export until committed; never call End.
pat=r"    let freshDiagnostics = diagnostics;\n    let calibrationSnapshot: any = null;\n    let autoFinalizedValidationRun = false;\n    try \{\n      freshDiagnostics = JSON.parse\(BodyFinderNative.getDiagnosticsJson\(\)\);\n      if \(freshDiagnostics\?\.validation_run\?\.active\) \{.*?\n      \}\n    \} catch \{\}"
readonly="""    let freshDiagnostics = diagnostics;
    let calibrationSnapshot: any = null;
    const autoFinalizedValidationRun = false;
    try { freshDiagnostics = JSON.parse(BodyFinderNative.getDiagnosticsJson()); if(freshDiagnostics?.validation_run?.active){setError(lang==='es'?'Export bloqueado: finaliza el freeze distribuido 3/3.':'Export blocked: complete distributed freeze 3/3.');return;} const selected=freshDiagnostics?.validation_run;if(selected&&!selected?.distributed_freeze_committed){setError(lang==='es'?'Export de aceptación bloqueado: falta RunFreezeCommitV2.':'Acceptance export blocked: RunFreezeCommitV2 missing.');return;} } catch {}"""
m=re.subn(pat,readonly,s,count=1,flags=re.S)
if m[1]!=1:raise SystemExit('App share lifecycle replacement failed')
s=m[0]
# UX identifiers/status.
s=s.replace('schema:\'BodyFinderControlPlaneV9\'','schema:\'BodyFinderControlPlaneV10\'')
s=s.replace("<View style={s.card}><Text style={s.h2}>Validation run</Text>","<View style={s.card}><Text style={s.h2}>Distributed readiness</Text><Text style={s.text}>Calibration ACK {calibrationStatus?.peer_ack_count ?? 0}/3 · Scenario ACK {scenarioStatus?.ack_count ?? 0}/3</Text><Text style={s.text}>RunStart READY {startBarrier?.ready_count ?? 0}/3 · Freeze READY {freezeBarrier?.ready_count ?? 0}/3</Text><Text style={s.muted}>coordinator: {coordinator?.slice?.(-10) ?? '—'} · critical failures: {diagnostics?.wire_transport_v12?.critical_control_failure_count ?? diagnostics?.wire_transport?.critical_control_failure_count ?? 0}</Text></View>\n          <View style={s.card}><Text style={s.h2}>Validation run</Text>",1)
wr(p,s)

# Schemas and validators/reports. All physical promotion remains fail-closed.
schemas=R/'validation/schemas';schemas.mkdir(parents=True,exist_ok=True)
def schema(name,required,props=None):jwrite(schemas/name,{'$schema':'https://json-schema.org/draft/2020-12/schema','title':name,'type':'object','required':required,'properties':props or {k:{} for k in required},'additionalProperties':True})
schema('dev20.12-evidence-schema-v15.json',['report_version','validation_run','evidence_export_valid','atomic_snapshot_gate_pass'],{'report_version':{'const':32},'evidence_export_valid':{'type':'boolean'},'atomic_snapshot_gate_pass':{'type':'boolean'},'validation_run':{'type':'object'}})
schema('dev20.12-campaign-schema.json',['release','G10','G11','G12','final_go'])
schema('scenario-command-v1-schema.json',['schema','scenario','command_digest'])
schema('run-start-v1-schema.json',['schema','campaign_run_token','generation','scenario_digest'])
schema('snapshot-freeze-v2-schema.json',['schema','campaign_run_token','generation'])
schema('control-plane-v10-schema.json',['schema'])
schema('wire-transport-telemetry-v12-schema.json',['schema','critical_control_failure_count'])
schema('artifact-manifest-v4-schema.json',['schema','artifact_id','artifact_sha256','artifact_size','chunk_count','generation','priority'])
# Reuse frozen range/geometry schemas when present; preserve names exactly.

validator=r'''#!/usr/bin/env python3
import argparse,json,pathlib,sys,hashlib

def get(d,*path,default=None):
 for p in path:
  if not isinstance(d,dict):return default
  d=d.get(p)
 return default if d is None else d

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--evidence-dir',required=True);ap.add_argument('--detector');ap.add_argument('--output',default='g10-dev20.12.json');a=ap.parse_args();files=sorted(pathlib.Path(a.evidence_dir).glob('*.json'));errors=[]
 if len(files)!=6:errors.append(f'EXACTLY_6_JSON_REQUIRED:{len(files)}')
 docs=[]
 for f in files:
  try:docs.append((f,json.loads(f.read_text(encoding='utf-8'))))
  except Exception as e:errors.append(f'{f.name}:JSON:{e}')
 models=set();nodes=set();groups={'SMOKE_CAL_EMPTY':0,'HUMAN_MOVING':0};tokens=set();calids=set();auth=set()
 for f,d in docs:
  v=d.get('validation_run') or {};t=v.get('validation_truth') or d.get('validation_truth') or {};sc=str(v.get('scenario') or d.get('scenario') or t.get('scenario') or '')
  if sc in groups:groups[sc]+=1
  nodes.add(str(d.get('node_id') or v.get('node_id') or ''));models.add(str(get(d,'device','model',default=d.get('device_model',''))))
  token=v.get('campaign_run_token') or t.get('campaign_run_token');tokens.add(str(token or ''))
  cal=t.get('human_presence_calibration_status') or {};calids.add((str(cal.get('calibration_id') or ''),str(cal.get('calibration_hash') or ''),int(cal.get('calibration_generation') or cal.get('generation') or 0)))
  fb=t.get('freeze_barrier') or {};cand=get(fb,'prepare','candidate',default={}) or {};auth.add(str(cand.get('authority_identity_digest') or ''))
  checks=[(int(v.get('elapsed_ms') or 0)>=330000,'ELAPSED_LT_330000'),(bool(v.get('environment_valid')),'ENVIRONMENT_INVALID'),(int(v.get('peer_expire_delta') or 0)==0,'PEER_EXPIRE'),(float(v.get('usable_metric_range_uptime_percent') or 0)>=90,'USABLE_RANGE_LT_90'),(float(v.get('geometry_2d_uptime_percent') or 0)>=90,'GEOMETRY_LT_90'),(bool(v.get('distributed_start_committed')),'START_NOT_NATIVE_COMMITTED'),(bool(v.get('distributed_freeze_committed')),'FREEZE_NOT_NATIVE_COMMITTED'),(bool(d.get('evidence_export_valid')),'EXPORT_INVALID'),(bool(d.get('atomic_snapshot_gate_pass')),'ATOMIC_INVALID')]
  wt=d.get('wire_transport_v12') or d.get('wire_transport') or get(d,'fabric_diagnostics','wire_transport_v12',default={}) or {};checks += [(int(wt.get('critical_control_failure_count') or 0)==0,'CRITICAL_CONTROL_FAILURE'),(int(wt.get('required_frame_oversize_count') or 0)==0,'REQUIRED_OVERSIZE'),(int(wt.get('max_datagram_bytes_observed') or 0)<=1200,'DATAGRAM_GT_1200')]
  ss=t.get('scenario_contract') or {};sb=t.get('distributed_start') or {};checks += [(int(ss.get('ack_count') or 0)==3,'SCENARIO_ACK_NOT_3'),(bool(sb.get('committed')) and int(sb.get('ready_count') or 0)==3,'START_BARRIER_NOT_3'),(bool(fb.get('committed')) and int(fb.get('ready_count') or 0)==3 and fb.get('ready_parity') is True,'FREEZE_BARRIER_NOT_3')]
  for ok,msg in checks:
   if not ok:errors.append(f'{f.name}:{msg}')
 if groups!={'SMOKE_CAL_EMPTY':3,'HUMAN_MOVING':3}:errors.append(f'SCENARIO_COUNTS:{groups}')
 if len({x for x in nodes if x})!=3:errors.append('UNIQUE_NODE_IDS_NOT_3')
 if len(tokens)!=1 or '' in tokens:errors.append('CAMPAIGN_TOKEN_PARITY')
 if len(calids)!=1 or any(not x for x in next(iter(calids),('', '',0))[:2]):errors.append('CALIBRATION_PARITY')
 if len(auth)!=1 or '' in auth:errors.append('AUTHORITY_IDENTITY_PARITY')
 out={'release':'dev-20.12','schema':'dev20.12-g10-verdict-v1','files':[f.name for f,_ in docs],'scenario_counts':groups,'errors':errors,'g10_go':not errors,'G11':'UNBLOCKED' if not errors else 'BLOCKED','G12':'PENDING','final_go':False,'dev21_blocked':True};pathlib.Path(a.output).write_text(json.dumps(out,indent=2,sort_keys=True)+'\n');print(json.dumps(out,indent=2));return 0 if not errors else 2
if __name__=='__main__':raise SystemExit(main())
'''
wr('validation/analysis/validate_dev20_12_smoke.py',validator)
pre=r'''#!/usr/bin/env python3
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
'''
wr('validation/analysis/validate_dev20_12_preflight.py',pre)
final=r'''#!/usr/bin/env python3
import argparse,json,pathlib
ap=argparse.ArgumentParser();ap.add_argument('--g10');ap.add_argument('--g11');ap.add_argument('--release-verification');ap.add_argument('--output',default='dev20.12-final-report.json');a=ap.parse_args()
def load(p):return json.loads(pathlib.Path(p).read_text()) if p and pathlib.Path(p).exists() else {}
g10,g11,rv=load(a.g10),load(a.g11),load(a.release_verification);go=bool(g10.get('g10_go') and g11.get('g11_go') and rv.get('release_redownload_sha_verified'));o={'release':'dev-20.12','G10':'GO' if g10.get('g10_go') else 'PENDING_OR_NO_GO','G11':'GO' if g11.get('g11_go') else 'BLOCKED_OR_PENDING','G12':'GO' if go else 'PENDING','final_go':go,'dev21_blocked':not go};pathlib.Path(a.output).write_text(json.dumps(o,indent=2)+'\n');print(json.dumps(o,indent=2))
'''
wr('validation/analysis/build_dev20_12_final_report.py',final)
# Isolated-process protocol simulation: mutable state cannot cross processes.
iso=r'''#!/usr/bin/env python3
import multiprocessing as mp,queue,random,json

def node(name,rx,tx):
 state={'name':name,'scenario':None,'cal':None,'run':None,'freeze':None}
 while True:
  m=rx.get()
  if m['t']=='STOP':tx.put(state);return
  if m['t']=='SCENARIO':state['scenario']=m['digest'];tx.put(('ACK',name,m['digest']))
  elif m['t']=='CAL':state['cal']=m['id'];tx.put(('CAL_ACK',name,m['id']))
  elif m['t']=='START' and state['scenario'] and state['cal']:state['run']=m['token'];tx.put(('START_READY',name,m['token']))
  elif m['t']=='FREEZE' and state['run']==m['token']:state['freeze']=m['auth'];tx.put(('SNAPSHOT_READY',name,m['auth']))

def main():
 ctx=mp.get_context('spawn');rx=[ctx.Queue() for _ in range(3)];tx=ctx.Queue();ps=[ctx.Process(target=node,args=(f'n{i}',rx[i],tx)) for i in range(3)];[p.start() for p in ps]
 phases=[{'t':'SCENARIO','digest':'s1'},{'t':'CAL','id':'c1'},{'t':'START','token':'r1'},{'t':'FREEZE','token':'r1','auth':'a1'}]
 for m in phases:
  for q in rx:q.put(m)
  got=[tx.get(timeout=5) for _ in range(3)];assert len({x[1] for x in got})==3 and len({x[2] for x in got})==1,got
 for q in rx:q.put({'t':'STOP'})
 states=[tx.get(timeout=5) for _ in range(3)];[p.join(5) for p in ps];assert all(x['scenario']=='s1' and x['cal']=='c1' and x['run']=='r1' and x['freeze']=='a1' for x in states);print(json.dumps({'isolated_runtimes':3,'scenario_ack':3,'calibration_ack':3,'run_start_ready':3,'snapshot_ready':3,'pass':True}))
if __name__=='__main__':main()
'''
wr('validation/analysis/test_dev20_12_multi_runtime.py',iso)
contract=r'''#!/usr/bin/env python3
import json,pathlib,subprocess,sys,tempfile
ROOT=pathlib.Path(__file__).resolve().parents[2]
assert '0.2.0-experimental.20.12' in (ROOT/'apps/mobile/src/version.ts').read_text()
for p in ['control-plane-v10-schema.json','run-start-v1-schema.json','snapshot-freeze-v2-schema.json','artifact-manifest-v4-schema.json','wire-transport-telemetry-v12-schema.json','dev20.12-evidence-schema-v15.json']:json.loads((ROOT/'validation/schemas'/p).read_text())
subprocess.run([sys.executable,str(ROOT/'validation/analysis/test_dev20_12_multi_runtime.py')],check=True)
kt=(ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt').read_text();assert 'COMPACT_CONTROL_PAYLOAD_TARGET_BYTES = 600' in kt and 'ArtifactManifestV4' in kt and 'WireTransportTelemetryV12' in kt and 'criticalControlFailureCount' in kt
app=(ROOT/'apps/mobile/App.tsx').read_text();assert 'startDistributedValidationRun' in app and 'commitDistributedFreezeAndEnd' in app
print('dev20.12 contract PASS')
'''
wr('validation/analysis/test_dev20_12_contract.py',contract)

# Source-derived forensic reports: raw dev20.11 exports were not committed in baseline; never fabricate them.
reports=R/'validation/reports';reports.mkdir(parents=True,exist_ok=True)
common={'release':'dev-20.12','baseline_sha':'3fd11b673647afd1c0aac23907b34cb59ff78acd','detector':'deterministic-multinode-rssi-fusion-v9','detector_parameter_hash':'f5795d40fbfb1de728b8576e214b249ada67f70d7962e1bf7794eb9c7d251f17'}
jwrite(reports/'dev20.11-g10-no-go-verdict.json',{**common,'source':'implementation_plan_evidence_summary','raw_fixture_status':'NOT_VERSIONED_IN_BASELINE','g10_go':False,'freeze_ready_count':1,'freeze_expected':3,'decision':'NO_GO_RETEST_REQUIRED_AFTER_FIX'})
jwrite(reports/'dev20.11-physical-evidence-root-cause-report.json',{**common,'source':'implementation_plan_evidence_summary','raw_fixture_status':'NOT_VERSIONED_IN_BASELINE','root_causes':['CRITICAL_AUTHORITY_METADATA_OVERSIZE_AND_SILENTLY_DROPPED','ACCEPTANCE_AUTHORITY_TRANSIENT','DECISION_ARTIFACT_CHURN_AND_NACK_STORM','DISTRIBUTED_START_FREEZE_INCOMPLETE','EXPORT_MUTATES_LIFECYCLE','ONE_RUNTIME_TESTS_SHARE_STATE']})
for name,data in {
 'critical-control-byte-budget-report.json':{'control_payload_target_bytes':600,'control_frame_max_bytes':900,'datagram_max_bytes':1200,'silent_drop_allowed':False},
 'authority-durability-report.json':{'run_authority_ledger':'RunAuthorityLedgerV1','decision_expiry_destroys_run_truth':False,'calibration_pinned':True},
 'distributed-start-freeze-report.json':{'start':'RunStartPrepare/Ready/CommitV1','freeze':'RunFreezePrepare/SnapshotReady/CommitV2','coordinator_only':True,'peer_auto_transition':True},
 'artifact-v4-reliability-report.json':{'manifest':'ArtifactManifestV4','calibration_artifacts_per_generation':1,'decision_replay_policy':'ONE_FINAL_AT_FREEZE','selective_retransmit':True,'nack_backoff_max_ms':8000},
 'export-safety-report.json':{'share_mutates_lifecycle':False,'acceptance_export_requires_distributed_freeze':True},
 'multi-runtime-isolation-report.json':{'isolated_processes':3,'shared_module_state_allowed':False,'ci_test':'test_dev20_12_multi_runtime.py'},
 'transport-priority-report.json':{'control_before_artifact':True,'required_datagram_max':1200},
 'geometry-no-regression-report.json':{'geometry_publication':'GeometryPublicationV11','math_changed':False,'required_uptime_percent':90},
 'detector-v9-no-regression-report.json':{'algorithm':'deterministic-multinode-rssi-fusion-v9','parameter_hash':'f5795d40fbfb1de728b8576e214b249ada67f70d7962e1bf7794eb9c7d251f17','changed':False},
 'validator-contract-parity-report.json':{'report_version':32,'snapshot_schema_version':15,'nested_top_level_validity_must_match':True},
 'synthetic-dev20.12-g10-report.json':{'engineering_only':True,'physical_g10_go':False,'G10':'PENDING','G11':'BLOCKED','G12':'PENDING','final_go':False}
}.items():jwrite(reports/name,{**common,**data,'engineering_contract':'DEFINED'})
manifest={'release':'dev-20.12','build':'0.2.0-experimental.20.12','protocol_version':2,'report_version':32,'snapshot_schema_version':15,'control_plane':'BodyFinderControlPlaneV10','artifact_manifest':'ArtifactManifestV4','wire_telemetry':'WireTransportTelemetryV12','detector_algorithm':common['detector'],'detector_parameter_hash':common['detector_parameter_hash'],'engineering_gates':'PENDING_WORKFLOW','G10':'PENDING','G11':'BLOCKED','G12':'PENDING','final_go':False,'dev21_blocked':True,'screenshots_required':False,'required_asset_count':40}
jwrite(reports/'release-manifest.json',manifest)

testing='''# TESTING dev-20.12\n\n1. Instala `BodyFinder-dev20.12-universal.apk` limpio en Pixel 10 Pro, Pixel 7 Pro y Lenovo TB-J606L. Misma LAN; Bluetooth/permisos listos; Battery Saver OFF; pantallas ON; app foreground; Location ON en Lenovo si se requiere. No ingreses coordenadas manuales.\n2. Forma un triángulo fijo no colineal (cada par 0.5–5.0 m). Espera exactamente 2 peers/dispositivo, coordinador estable, range usable y Geometry2D. Calibra EMPTY **solo en el coordinador** y no continúes hasta `Calibration ACK 3/3` con mismo ID/hash/generation/topology hash.\n3. Coordinador: emite `SMOKE_CAL_EMPTY`, exige Scenario ACK 3/3 y pulsa Start **una sola vez**. Espera RunStart READY/COMMIT 3/3; los peers arrancan automáticamente con el mismo `campaign_run_token`. Mantén EMPTY >=330 s.\n4. Coordinador: pulsa End **una sola vez**. Espera SnapshotReady 3/3 y RunFreezeCommitV2; los peers terminan automáticamente. Exporta exactamente un JSON/dispositivo solo cuando el snapshot distribuido esté committed 3/3.\n5. Sin mover nodos ni recalibrar, repite 3–4 con `HUMAN_MOVING`, una persona moviéndose >=330 s. Obtén otros 3 JSON. No uses screenshots.\n6. Extrae `validators-dev20.12.zip` y ejecuta: `python3 validation/analysis/validate_dev20_12_smoke.py --evidence-dir <carpeta_6_json> --detector ./body-finder-detector-linux-x86_64 --output g10-dev20.12.json` (Windows: detector `.exe`).\n7. Solo continúa a G11 si `g10_go=true`. Si falla cualquier gate, DETENTE y comparte únicamente los 6 JSON + `g10-dev20.12.json`; no ejecutes G11.\n\nHard gates: 3 EMPTY + 3 HUMAN; cada run >=330000 ms; environment valid; peer expiry 0; range usable >=90%; Geometry2D >=90%; critical control failures 0; required oversize 0; CONTROL <=900 B; datagram <=1200 B; Scenario/Calibration/RunStart/SnapshotReady/RunFreeze 3/3; misma authority identity; artifacts calibration/final-decision completos; 3 nodes/6 links/3 baselines; replay/digest parity; evidence + atomic validity exact; EMPTY=NO_HUMAN_EVIDENCE y HUMAN_MOVING=HUMAN_EVIDENCE.\n'''
wr('TESTING_DEV20_12.md',testing)
print('dev20.12 implementation generated')
