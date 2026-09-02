import { Advertisement } from './autogeometry';
import BodyFinderNative from '../modules/body-finder-native';
import { DETECTOR_ALGORITHM, DETECTOR_PARAMETER_HASH, DETECTOR_V8 } from './detectorParameters';
import { deterministicCoordinator, getAuthorityControlPublication, getAuthorityStatus } from './authority';

export type PresencePrediction = 'HUMAN_EVIDENCE' | 'NO_HUMAN_EVIDENCE' | 'INDETERMINATE';
export type CalibrationState = 'UNCALIBRATED'|'CALIBRATING'|'READY'|'INVALID'|'WAIT_COORDINATOR'|'STALE_AUTHORITY';
export type PresenceEstimate = {
  prediction: PresencePrediction; human_confidence: number; evidence_quality: string; fused_score: number;
  contributing_nodes: number; contributing_links: number; physical_baselines: number; reason: string;
  calibration_state: CalibrationState; calibration_id?: string|null; calibration_hash?: string|null;
  algorithm_version: string; parameter_hash: string; window_id: string; decision_id?: string; canonical_digest?: string;
  authoritative: boolean; source: string; [key: string]: any;
};
type Sample={receive_wall_ms:number;source_monotonic_ns:number|null;rssi_dbm:number};
type Link={link_id:string;observer_node_id:string;peer_node_id:string;samples:Sample[]};
type Membership={
  sessionId:string; nodeIds:string[]; observed:Set<string>; lastSeen:Record<string,number>; scores:Record<string,number>;
  unexpectedSince:Record<string,number>; coordinator:string|null; coordinatorGeneration:number; coordinatorMissingSince:number|null;
  instanceByNode:Record<string,string>; transitions:{wall_ms:number;kind:string;node_id:string;instance_epoch:string;reason:string}[];
};
type CalState={
  state:CalibrationState; generation:number; coordinator:string|null; topology:string|null; topologyHash:string; started:number; artifact:any|null;
  reason:string; expectedCohort:string[]; publicationSequence:number; lastAuthorityWallMs:number; coordinatorGeneration:number; authorityDigest:string;
};
type CachedDecision={decision:PresenceEstimate;receivedWallMs:number;sequence:number};

const HISTORY_MS=90_000;
const DECISION_FRESH_MS=30_000;
const DECISION_EXPIRED_MS=60_000;
const history=new Map<string,Sample[]>();
const lastSource=new Map<string,number>();
const membershipBySession=new Map<string,Membership>();
const latestDecisionBySession=new Map<string,CachedDecision>();
const decisionSequenceBySession=new Map<string,number>();
let lastLocalNodeId:string|null=null;
const calibrationByScope=new Map<string,CalState>();
let activeCalibrationScope='__bootstrap__';
function blankCalibration():CalState{return{state:'UNCALIBRATED',generation:0,coordinator:null,topology:'',topologyHash:'',started:0,artifact:null,reason:'NOT_CALIBRATED',expectedCohort:[],publicationSequence:0,lastAuthorityWallMs:0,coordinatorGeneration:0,authorityDigest:''}}
function activateCalibrationScope(nodes:Advertisement[],localNodeId:string|null){const sid=currentSession(nodes),key=`${sid}::${localNodeId??lastLocalNodeId??'unknown'}`;if(key===activeCalibrationScope)return;calibrationByScope.set(activeCalibrationScope,cal);cal=calibrationByScope.get(key)??blankCalibration();activeCalibrationScope=key;lastLocalNodeId=localNodeId??lastLocalNodeId}
let cal:CalState={state:'UNCALIBRATED',generation:0,coordinator:null,topology:null,topologyHash:'',started:0,artifact:null,reason:'EMPTY_CAL_REQUIRED',expectedCohort:[],publicationSequence:0,lastAuthorityWallMs:0,coordinatorGeneration:0,authorityDigest:''};

function pair(a:string,b:string){return a<b?`${a}::${b}`:`${b}::${a}`}
function sessionId(nodes:Advertisement[]){const counts=new Map<string,number>();for(const n of nodes){if(n.protocol_version!==2||!n.session_id)continue;counts.set(n.session_id,(counts.get(n.session_id)??0)+1)}return [...counts.entries()].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0]))[0]?.[0]??null}
function freshNodes(nodes:Advertisement[],sid:string|null){return nodes.filter(n=>n.protocol_version===2&&n.session_id===sid&&Boolean(n.node_id)&&Number((n as any).membership_lease_age_ms??0)<=15_000&&String((n as any).membership_lease_state??'LIVE')!=='EXPIRED')}
function updateMembership(nodes:Advertisement[]):Membership|null{
  const sid=sessionId(nodes); if(!sid)return null; const now=Date.now();
  let m=membershipBySession.get(sid);
  if(!m){m={sessionId:sid,nodeIds:[],observed:new Set(),lastSeen:{},scores:{},unexpectedSince:{},coordinator:null,coordinatorGeneration:1,coordinatorMissingSince:null,instanceByNode:{},transitions:[]};membershipBySession.set(sid,m)}
  for(const n of freshNodes(nodes,sid)){const id=String(n.node_id),inst=String((n as any).instance_epoch??'').trim();if(!inst||inst==='legacy')continue;const prior=m.instanceByNode[id];if(prior&&prior!==inst){m.transitions.push({wall_ms:now,kind:'REPLACE',node_id:id,instance_epoch:inst,reason:'NEW_INSTANCE_EPOCH'});m.transitions=m.transitions.slice(-64)}m.instanceByNode[id]=inst;m.observed.add(id);m.lastSeen[id]=now;m.scores[id]=Number(n.coordinator_score??0)}
  for(const id of m.nodeIds.slice()){if(now-(m.lastSeen[id]??0)>15_000){m.nodeIds=m.nodeIds.filter(x=>x!==id);m.transitions.push({wall_ms:now,kind:'PRUNE',node_id:id,instance_epoch:m.instanceByNode[id]??'unknown',reason:'LEASE_EXPIRED'});delete m.instanceByNode[id]}}
  const activeIds=[...new Set(freshNodes(nodes,sid).map(n=>String(n.node_id)))].sort();if(m.nodeIds.length<3){for(const id of activeIds)if(!m.nodeIds.includes(id)&&m.nodeIds.length<3)m.nodeIds.push(id)}m.nodeIds=m.nodeIds.filter(id=>activeIds.includes(id)).sort()
  if(!m.nodeIds.length)m.nodeIds=[...m.observed].sort();
  const active=new Set(freshNodes(nodes,sid).map(n=>String(n.node_id)));
  for(const id of m.observed){if(!m.nodeIds.includes(id)){if(active.has(id)&&!m.unexpectedSince[id])m.unexpectedSince[id]=now;if(!active.has(id))delete m.unexpectedSince[id]}}
  const av=getAuthorityStatus(nodes,lastLocalNodeId).view;m.coordinator=av?.elected_coordinator??null;m.coordinatorGeneration=av?.coordinator_generation??Math.max(1,m.coordinatorGeneration);m.coordinatorMissingSince=null;
  return m;
}
function stableCohort(nodes:Advertisement[]){return updateMembership(nodes)?.nodeIds.slice().sort()??[]}
function cohortFingerprint(cohort:string[]){const directed:string[]=[];for(const a of cohort)for(const b of cohort)if(a!==b)directed.push(`${a}::${b}`);return cohort.join(',')+'|'+directed.sort().join(',')}
function transportStates(nodes:Advertisement[]){
  const m=updateMembership(nodes);if(!m)return[];const now=Date.now();const active=new Set(freshNodes(nodes,m.sessionId).map(n=>String(n.node_id)));
  return m.nodeIds.map(id=>({node_id:id,logical_member:true,transport_liveness_state:active.has(id)?'LIVE':'DEGRADED',last_seen_age_ms:m.lastSeen[id]?Math.max(0,now-m.lastSeen[id]):null}));
}
function confirmedMembershipChanges(nodes:Advertisement[]){
  const m=updateMembership(nodes);if(!m||m.nodeIds.length!==3)return[] as string[];const now=Date.now();
  return Object.entries(m.unexpectedSince).filter(([,since])=>now-since>=DETECTOR_V8.membershipChangeGraceMs).map(([id])=>id).sort();
}
export function electStableCoordinator(nodes:Advertisement[],localNodeId:string|null){activateCalibrationScope(nodes,localNodeId);lastLocalNodeId=localNodeId;updateMembership(nodes);return deterministicCoordinator(nodes,localNodeId)}

function ingest(nodes:Advertisement[]):Link[]{const now=Date.now();for(const n of nodes){for(const r of n.ranges??[]){const v=Number(r.rssi_dbm);if(!Number.isFinite(v)||v>0||v<-126)continue;const observer=String(r.observer_node_id||n.node_id||'');const peer=String(r.peer_node_id||'');if(!observer||!peer)continue;const id=`${observer}::${peer}`;const source=Number((r as any).source_observation_monotonic_ns??r.monotonic_ns??0);if(source>0&&lastSource.get(id)===source)continue;if(source>0)lastSource.set(id,source);const q=history.get(id)??[];q.push({receive_wall_ms:now,source_monotonic_ns:source>0?source:null,rssi_dbm:v});history.set(id,q.filter(s=>now-s.receive_wall_ms<=HISTORY_MS).slice(-240));}}return [...history.entries()].map(([id,samples])=>{const [observer,peer]=id.split('::');return{link_id:id,observer_node_id:observer,peer_node_id:peer,samples}}).sort((a,b)=>a.link_id.localeCompare(b.link_id))}
function expectedLinks(links:Link[],cohort:string[]){const ids=new Set<string>();for(const a of cohort)for(const b of cohort)if(a!==b)ids.add(`${a}::${b}`);return links.filter(l=>ids.has(l.link_id))}
function topology(links:Link[],cohort:string[]){const live=expectedLinks(links,cohort).filter(l=>l.samples.length&&Date.now()-l.samples.at(-1)!.receive_wall_ms<DETECTOR_V8.transportEvidenceFreshMs);const nodes=new Set(live.map(l=>l.observer_node_id));const baselines=new Set(live.map(l=>pair(l.observer_node_id,l.peer_node_id)));return{ok:cohort.length===3&&nodes.size>=3&&live.length>=6&&baselines.size>=3,fingerprint:cohortFingerprint(cohort),links:live,nodes:nodes.size,baselines:baselines.size}}
function native(input:any){try{const out=JSON.parse(BodyFinderNative.evaluateHumanPresenceJson(JSON.stringify(input)));if(out?.error)throw new Error(String(out.error));return out}catch(e:any){return{error:String(e?.message??e)}}}
function artifactFrom(node:Advertisement|undefined,id:string|null|undefined){if(!node||!id)return null;return (node as any)?.artifact_cache_v1?.[id]??null}
function computeTopologyHash(fingerprint:string){return BodyFinderNative.sha256Text(fingerprint)}
function canonicalTopologyHash(){return cal.topologyHash||computeTopologyHash(cal.topology||'')}
function assertCanonicalTopologyHash(value:string){if(!/^[0-9a-f]{64}$/i.test(value))throw new Error('TOPOLOGY_HASH_NOT_SHA256');return value}
function publicationFrom(nodes:Advertisement[],coordinatorNodeId:string|null){const coordinator=nodes.find(n=>n.node_id===coordinatorNodeId);const raw=(coordinator?.control_plane as any)?.calibration_meta_v10??null;if(raw?.schema==='CalibrationMetaWireV3')return{schema:'CalibrationMetaWireV3',session_id:raw.s,coordinator_id:raw.n,cg:Number(raw.cg),g:Number(raw.g),id:raw.i,hash:raw.h,artifact_id:`calibration:${raw.i}`,topology_hash:raw.t,seq:Number(raw.q),lease_ms:Number(raw.l),authority_digest:raw.d};return raw}
function calibrationMetaWire(){if(!cal.artifact||!cal.coordinator)return null;const topology_hash=assertCanonicalTopologyHash(canonicalTopologyHash());return{schema:'CalibrationMetaWireV3',s:cal.artifact.session_id,n:cal.coordinator,cg:cal.coordinatorGeneration,g:cal.generation,i:cal.artifact.calibration_id,h:cal.artifact.calibration_hash,t:topology_hash,q:cal.publicationSequence,l:DETECTOR_V8.authorityPublicationLeaseMs,d:cal.authorityDigest}}
function calibrationAckWire(localNodeId:string|null,sid:string,topology_hash:string){return cal.artifact&&localNodeId&&cal.expectedCohort.includes(localNodeId)?{schema:'CalibrationAckWireV3',s:sid,n:localNodeId,c:cal.coordinator,cg:cal.coordinatorGeneration,g:cal.generation,i:cal.artifact.calibration_id,h:cal.artifact.calibration_hash,t:assertCanonicalTopologyHash(topology_hash),d:cal.authorityDigest}:null}
function currentSession(nodes:Advertisement[]){return sessionId(nodes)??'body-finder-lab'}
function decisionFreshness(receivedWallMs:number){const age=Math.max(0,Date.now()-receivedWallMs);return age<=DECISION_FRESH_MS?'FRESH':age<=DECISION_EXPIRED_MS?'STALE':'EXPIRED'}
function fallback(reason:string,state:CalibrationState=cal.state,extra:Record<string,unknown>={}):PresenceEstimate{return{prediction:'INDETERMINATE',human_confidence:0.5,evidence_quality:'LOW',fused_score:0,contributing_nodes:0,contributing_links:0,physical_baselines:0,reason,calibration_state:state,calibration_id:cal.artifact?.calibration_id??null,calibration_hash:cal.artifact?.calibration_hash??null,algorithm_version:DETECTOR_ALGORITHM,parameter_hash:DETECTOR_PARAMETER_HASH,window_id:String(Math.floor(Date.now()/2000)*2000),authoritative:false,source:'diagnostic_fail_closed',logical_membership_state:{expected_cohort:cal.expectedCohort},transport_liveness_state:extra.transport_liveness_state??[],...extra}}

function syncAuthoritativeCalibration(nodes:Advertisement[],coordinatorNodeId:string|null,localNodeId:string|null){
  lastLocalNodeId=localNodeId;if(!coordinatorNodeId||coordinatorNodeId===localNodeId)return;const authority=getAuthorityStatus(nodes,localNodeId),coordinator=nodes.find(n=>n.node_id===coordinatorNodeId),p=publicationFrom(nodes,coordinatorNodeId),now=Date.now();
  const artifact=p?.artifact_id?artifactFrom(coordinator,p.artifact_id):null;
  if(p?.schema==='CalibrationMetaWireV3'&&artifact?.calibration_hash===p?.hash&&authority.view&&p?.authority_digest===authority.view.authority_view_digest&&p?.session_id===authority.view.session_id&&p?.coordinator_id===coordinatorNodeId){
    const incomingCg=Number(p.cg??0),incomingCal=Number(p.g??0),incomingSeq=Number(p.seq??0);
    const sameOrNewer=incomingCg>cal.coordinatorGeneration||(incomingCg===cal.coordinatorGeneration&&incomingCal>=cal.generation);const ordered=incomingCg>cal.coordinatorGeneration||incomingSeq>=cal.publicationSequence;
    if(sameOrNewer&&ordered){const receivedTopologyHash=assertCanonicalTopologyHash(String(p.topology_hash??''));cal={...cal,state:'READY',generation:incomingCal,coordinator:coordinatorNodeId,topologyHash:receivedTopologyHash,artifact,reason:'AUTHORITATIVE_CALIBRATION_FINAL_V10_COMPLETE',expectedCohort:authority.view.cohort.map((x:any)=>String(x.node_id)).sort(),publicationSequence:incomingSeq,lastAuthorityWallMs:now,coordinatorGeneration:incomingCg,authorityDigest:String(p.authority_digest)}}
  }else if(p?.schema==='CalibrationMetaWireV3'&&!artifact&&!cal.artifact){cal={...cal,state:'WAIT_COORDINATOR',coordinator:coordinatorNodeId,reason:'CALIBRATION_FINAL_V10_PENDING'}}
  else if(cal.artifact&&cal.lastAuthorityWallMs&&now-cal.lastAuthorityWallMs>DETECTOR_V8.authorityPublicationLeaseMs){cal={...cal,state:'STALE_AUTHORITY',reason:'AUTHORITY_PUBLICATION_LEASE_EXPIRED_CALIBRATION_PRESERVED'}}
}
function adoptCoordinatorIfNeeded(nodes:Advertisement[],coordinatorNodeId:string|null,localNodeId:string|null){
  if(!coordinatorNodeId||coordinatorNodeId!==localNodeId||!cal.artifact)return;const m=updateMembership(nodes),authority=getAuthorityStatus(nodes,localNodeId);if(!m||!authority.view)return;if(cal.authorityDigest&&cal.authorityDigest!==authority.view.authority_view_digest){cal={...cal,state:'INVALID',artifact:null,reason:'AUTHORITY_GENERATION_CHANGED_RECALIBRATION_REQUIRED',authorityDigest:authority.view.authority_view_digest,coordinator:coordinatorNodeId,coordinatorGeneration:authority.view.coordinator_generation};return}if(cal.coordinator!==coordinatorNodeId||cal.coordinatorGeneration<authority.view.coordinator_generation){cal={...cal,state:'INVALID',artifact:null,reason:'AUTHORITY_FAILOVER_RECALIBRATION_REQUIRED',authorityDigest:authority.view.authority_view_digest,coordinator:coordinatorNodeId,coordinatorGeneration:authority.view.coordinator_generation}}
}
function exactAck(node:Advertisement,id:string){
  if(!cal.artifact)return false;if(id===cal.coordinator)return true;
  const a=(node.control_plane as any)?.calibration_ack_v10;if(!a)return false;const topology_hash=canonicalTopologyHash();
  return Boolean(a.schema==='CalibrationAckWireV3'&&a.s===cal.artifact.session_id&&a.n===id&&a.c===cal.coordinator&&Number(a.g)===cal.generation&&Number(a.cg)===cal.coordinatorGeneration&&a.i===cal.artifact.calibration_id&&a.h===cal.artifact.calibration_hash&&a.t===topology_hash&&a.d===cal.authorityDigest);
}
function peerAckMatrix(nodes:Advertisement[]){
  return cal.expectedCohort.map(id=>{const n=nodes.find(x=>x.node_id===id),a=(n?.control_plane as any)?.calibration_ack_v10,local=id===cal.coordinator||id===lastLocalNodeId,valid=Boolean(n&&exactAck(n,id))||local;return{node_id:id,acknowledged:valid,ack_schema:local?'LOCAL_IMPLICIT_EXACT':a?.schema??null,observed_topology_hash:local?canonicalTopologyHash():a?.t??null,observed_calibration_id:local?cal.artifact?.calibration_id??null:a?.i??null,observed_calibration_hash:local?cal.artifact?.calibration_hash??null:a?.h??null,observed_coordinator_id:local?cal.coordinator:a?.c??null,observed_authority_digest:local?cal.authorityDigest:a?.d??null,rejection_reason:valid?null:(a?'CALIBRATION_ACK_BINDING_MISMATCH':'CALIBRATION_ACK_MISSING'),calibration_id:cal.artifact?.calibration_id??null,calibration_hash:cal.artifact?.calibration_hash??null,calibration_generation:cal.generation,coordinator_generation:cal.coordinatorGeneration}})
}

export function beginSessionPresenceCalibration(nodes:Advertisement[],coordinatorNodeId:string|null,localNodeId:string|null){
  activateCalibrationScope(nodes,localNodeId);lastLocalNodeId=localNodeId;const links=ingest(nodes),cohort=stableCohort(nodes),t=topology(links,cohort);
  const authority=getAuthorityStatus(nodes,localNodeId);if(!authority.consensus||authority.ack_count!==3||!authority.view){cal={...cal,state:'WAIT_COORDINATOR',reason:'AUTHORITY_CONSENSUS_REQUIRED_3_OF_3'};return cal}
  if(!coordinatorNodeId||coordinatorNodeId!==localNodeId){syncAuthoritativeCalibration(nodes,coordinatorNodeId,localNodeId);if(cal.artifact)return cal;cal={...cal,state:'WAIT_COORDINATOR',coordinator:coordinatorNodeId,reason:'CALIBRATION_MUST_BE_STARTED_ON_ELECTED_COORDINATOR'};return cal}
  if(cohort.length!==3||!t.ok){cal={...cal,state:'INVALID',coordinator:coordinatorNodeId,reason:'CALIBRATION_REQUIRES_3_NODES_6_LINKS_3_BASELINES'};return cal}
  const m=updateMembership(nodes);
  const sameAttempt=cal.state==='CALIBRATING'&&cal.coordinator===coordinatorNodeId&&cal.coordinatorGeneration===authority.view.coordinator_generation&&cal.authorityDigest===authority.view.authority_view_digest&&cal.topology===t.fingerprint&&JSON.stringify(cal.expectedCohort)===JSON.stringify(cohort);if(sameAttempt){cal={...cal,reason:'DUPLICATE_CALIBRATION_START_IDEMPOTENT'};return cal}
  cal={state:'CALIBRATING',generation:cal.generation+1,coordinator:coordinatorNodeId,topology:t.fingerprint,topologyHash:computeTopologyHash(t.fingerprint),started:Date.now(),artifact:null,reason:'COLLECTING_SYNCHRONIZED_EMPTY_BASELINE',expectedCohort:cohort,publicationSequence:0,lastAuthorityWallMs:Date.now(),coordinatorGeneration:authority.view.coordinator_generation,authorityDigest:authority.view.authority_view_digest};
  return cal
}
export function getSessionPresenceCalibration(nodes:Advertisement[]=[]){
  activateCalibrationScope(nodes,lastLocalNodeId);const matrix=peerAckMatrix(nodes),expected=cal.expectedCohort.length||3,ackCount=matrix.filter(x=>x.acknowledged).length;
  const authority=getAuthorityStatus(nodes,lastLocalNodeId),topologyHash=canonicalTopologyHash(),ackSymmetric=expected===3&&ackCount===3&&matrix.every((x:any)=>x.acknowledged);return{state:cal.state,generation:cal.generation,calibration_generation:cal.generation,coordinator_generation:cal.coordinatorGeneration,authority_digest:cal.authorityDigest,authority_consensus:authority.consensus,authority_ack_count:authority.ack_count,coordinator_node_id:cal.coordinator,topology_fingerprint:cal.topology,topology_hash:topologyHash,topology_hash_source:cal.topologyHash?'COORDINATOR_CANONICAL_OR_ECHO':'LOCAL_FINGERPRINT_HASH_ONCE',expected_cohort:cal.expectedCohort,started_wall_ms:cal.started,calibration_id:cal.artifact?.calibration_id??null,calibration_hash:cal.artifact?.calibration_hash??null,reason:cal.reason,publication_sequence:cal.publicationSequence,authority_lease_age_ms:cal.lastAuthorityWallMs?Date.now()-cal.lastAuthorityWallMs:null,peer_ack_matrix:matrix,peer_ack_count:ackCount,calibration_ack_symmetric:ackSymmetric,distributed_calibration_ready:cal.state==='READY'&&ackSymmetric,logical_membership_state:{cohort:cal.expectedCohort,current_instances:cal.expectedCohort.map(id=>({node_id:id,instance_epoch:updateMembership(nodes)?.instanceByNode[id]??null})),confirmed_change:confirmedMembershipChanges(nodes),transitions:updateMembership(nodes)?.transitions??[]},transport_liveness_state:transportStates(nodes)}
}
export function getCalibrationPublication(localNodeId:string|null){
  if(!cal.artifact||cal.coordinator!==localNodeId||!(cal.state==='READY'||cal.state==='STALE_AUTHORITY'))return null;cal.publicationSequence+=1;cal.lastAuthorityWallMs=Date.now();return calibrationMetaWire()
}
export function getControlPlanePublication(nodes:Advertisement[],coordinatorNodeId:string|null,localNodeId:string|null){
  activateCalibrationScope(nodes,localNodeId);lastLocalNodeId=localNodeId;syncAuthoritativeCalibration(nodes,coordinatorNodeId,localNodeId);adoptCoordinatorIfNeeded(nodes,coordinatorNodeId,localNodeId);const sid=currentSession(nodes),cm=getCalibrationPublication(localNodeId),cached=latestDecisionBySession.get(sid),topology_hash=canonicalTopologyHash();
  const ack=calibrationAckWire(localNodeId,sid,topology_hash);
  const dm=cached&&coordinatorNodeId===localNodeId&&cached.decision.authoritative&&cached.decision.canonical_digest?{schema:'DecisionMetaWireV2',s:sid,n:coordinatorNodeId,cg:cal.coordinatorGeneration,g:cached.decision.calibration_generation??cal.generation,ch:cached.decision.calibration_hash??cal.artifact?.calibration_hash??null,t:topology_hash,q:cached.sequence,i:cached.decision.decision_id,d:cached.decision.canonical_digest,p:cached.decision.prediction,nn:Number(cached.decision.contributing_nodes??0),ll:Number(cached.decision.contributing_links??0),bb:Number(cached.decision.physical_baselines??0)}:null;
  const da=cached&&localNodeId?{schema:'DecisionAckWireV2',s:sid,n:localNodeId,q:cached.sequence,i:cached.decision.decision_id??null,d:cached.decision.canonical_digest??null}:null;
  const artifacts:any[]=[];if(coordinatorNodeId===localNodeId&&cm&&cal.artifact)artifacts.push({artifact_id:`calibration:${cal.artifact.calibration_id}`,artifact_type:'CALIBRATION_FINAL_V10',generation:cal.generation,priority:'CALIBRATION_FINAL',supersedes_artifact_id:null,payload:cal.artifact});const authority=getAuthorityControlPublication(nodes,localNodeId);
  return{schema:'BodyFinderControlPlaneV11',session_id:sid,node_id:localNodeId,authority_view_v1:authority.authority_view_v1,authority_ack_v1:authority.authority_ack_v1,logical_membership_state:{schema:'LogicalMembershipWireV2',c:stableCohort(nodes)},calibration_meta_v10:cm,calibration_ack_v10:ack,decision_meta_v10:dm,decision_ack_v10:da,artifact_payloads_v1:artifacts}
}
export function getRunAuthorityLedger(nodes:Advertisement[],coordinatorNodeId:string|null,localNodeId:string|null){activateCalibrationScope(nodes,localNodeId);syncAuthoritativeCalibration(nodes,coordinatorNodeId,localNodeId);const sid=currentSession(nodes),cached=latestDecisionBySession.get(sid),d=cached?.decision??null;const authority=getAuthorityStatus(nodes,localNodeId);return{schema:'RunAuthorityLedgerV1',session_id:sid,node_id:localNodeId,authority_view:authority.view,authority_consensus:authority.consensus,authority_ack_count:authority.ack_count,authority_ledger_reason:cal.artifact?'PINNED_CALIBRATION':'CALIBRATION_MISSING',authority_ledger_age_ms:cached?Math.max(0,Date.now()-cached.receivedWallMs):null,calibration_id:cal.artifact?.calibration_id??null,calibration_hash:cal.artifact?.calibration_hash??null,calibration_generation:cal.generation,topology_hash:canonicalTopologyHash(),cohort:cal.expectedCohort,decision:d?{...d,decision_freshness_state:decisionFreshness(cached!.receivedWallMs)}:null}}

function maybeFreeze(nodes:Advertisement[],coordinatorNodeId:string|null,localNodeId:string|null,links:Link[]){
  if(cal.state!=='CALIBRATING'||coordinatorNodeId!==localNodeId)return;
  if(Date.now()-cal.started>DETECTOR_V8.calibrationTimeoutMs){cal={...cal,state:'INVALID',reason:'CALIBRATION_INSUFFICIENT_SUPPORT'};return}
  const t=topology(links,cal.expectedCohort);if(!t.ok)return;
  const selected=t.links.map(l=>({...l,samples:l.samples.filter(s=>s.receive_wall_ms>=cal.started)}));
  const starts=selected.map(l=>l.samples[0]?.receive_wall_ms??Infinity),ends=selected.map(l=>l.samples.at(-1)?.receive_wall_ms??-Infinity);const overlap=Math.min(...ends)-Math.max(...starts);
  if(selected.some(l=>l.samples.length<DETECTOR_V8.calibrationMinSamplesPerLink)||overlap<DETECTOR_V8.calibrationMinOverlapMs)return;
  const session=currentSession(nodes),calibrationId=`cal-d208-${cal.generation}-${coordinatorNodeId?.slice(-8)??'none'}-${cal.started}`;
  const out=native({operation:'BUILD_CALIBRATION',session_id:session,calibration_id:calibrationId,generation:cal.generation,topology_fingerprint:cal.topology,detector_parameter_hash:DETECTOR_PARAMETER_HASH,frozen_wall_ms:Date.now(),links:selected.map(l=>({...l,samples:l.samples.slice(-180)}))});
  if(out.calibration_state==='READY'&&out.artifact){cal={...cal,state:'READY',artifact:out.artifact,reason:'FROZEN_SYNCHRONIZED_EMPTY_CALIBRATION',lastAuthorityWallMs:Date.now()}}else{cal={...cal,state:'INVALID',artifact:null,reason:out.reason??'CALIBRATION_ENGINE_REJECTED'}}
}

export function estimateHumanPresence(nodes:Advertisement[],mode:'coordinator'|'diagnostic'='diagnostic',coordinatorNodeId:string|null=null,localNodeId:string|null=null):PresenceEstimate{
  lastLocalNodeId=localNodeId;const links=ingest(nodes);syncAuthoritativeCalibration(nodes,coordinatorNodeId,localNodeId);adoptCoordinatorIfNeeded(nodes,coordinatorNodeId,localNodeId);
  const transport=transportStates(nodes);
  if(mode!=='coordinator')return fallback(cal.state==='STALE_AUTHORITY'?cal.reason:(cal.artifact?'authoritative_calibration_mirrored_awaiting_decision':'awaiting_elected_coordinator_publication'),cal.state,{transport_liveness_state:transport});
  if(!coordinatorNodeId||coordinatorNodeId!==localNodeId)return fallback('not_elected_coordinator',cal.state,{transport_liveness_state:transport});
  maybeFreeze(nodes,coordinatorNodeId,localNodeId,links);
  if(cal.state!=='READY'||!cal.artifact)return fallback(cal.reason,cal.state,{transport_liveness_state:transport});
  const changed=confirmedMembershipChanges(nodes);if(changed.length){cal={...cal,state:'INVALID',reason:'CONFIRMED_SESSION_MEMBERSHIP_CHANGE_RECALIBRATION_REQUIRED'};return fallback(cal.reason,'INVALID',{logical_membership_change:changed,transport_liveness_state:transport})}
  const t=topology(links,cal.expectedCohort);if(!t.ok)return fallback('TRANSIENT_RF_OR_UDP_EVIDENCE_GAP_CALIBRATION_PRESERVED','READY',{transport_liveness_state:transport,logical_membership_state:{expected_cohort:cal.expectedCohort}});
  if(cal.artifact.detector_parameter_hash!==DETECTOR_PARAMETER_HASH){cal={...cal,state:'INVALID',artifact:null,reason:'DETECTOR_PARAMETER_HASH_CHANGED'};return fallback(cal.reason,'INVALID')}
  const now=Date.now(),start=Math.max(Number(cal.artifact.frozen_wall_ms)+250,now-DETECTOR_V8.observationWindowMs);
  const obs=expectedLinks(links,cal.expectedCohort).map(l=>({...l,samples:l.samples.filter(s=>s.receive_wall_ms>=start).slice(-240)}));
  const support=obs.map(l=>({link_id:l.link_id,actual_samples:l.samples.length,min_samples:DETECTOR_V8.observationMinSamplesPerLink,first_receive_wall_ms:l.samples[0]?.receive_wall_ms??null,last_receive_wall_ms:l.samples.at(-1)?.receive_wall_ms??null}));
  const insufficient=support.filter(s=>s.actual_samples<DETECTOR_V8.observationMinSamplesPerLink);
  if(obs.length!==6||insufficient.length)return fallback('OBSERVATION_SUPPORT_INCOMPLETE_DEADLINE_NOT_YET_ADMISSIBLE','READY',{observation_support:{window_ms:DETECTOR_V8.observationWindowMs,links:support,insufficient_links:insufficient.map(x=>x.link_id)},transport_liveness_state:transport});
  const input={operation:'INFER',session_id:currentSession(nodes),window_id:String(Math.floor(now/2000)*2000),window_start_wall_ms:Math.min(...obs.flatMap(l=>l.samples.map(s=>s.receive_wall_ms)),now),window_end_wall_ms:now,detector_parameter_hash:DETECTOR_PARAMETER_HASH,calibration:cal.artifact,acquisition_health:{environment_valid:true,acquisition_valid:true},links:obs};
  const out=native(input);if(out.error)return fallback(`canonical_engine_error:${out.error}`,'READY',{observation_support:{links:support},transport_liveness_state:transport});
  const publication=getCalibrationPublication(localNodeId);
  const result={...out,calibration_state:out.calibration_state??'READY',calibration_id:cal.artifact.calibration_id,calibration_hash:cal.artifact.calibration_hash,calibration_generation:cal.generation,coordinator_generation:cal.coordinatorGeneration,topology_fingerprint:cal.topology,expected_cohort:cal.expectedCohort,calibration_meta_v10:publication,peer_ack_matrix:peerAckMatrix(nodes),distributed_calibration_ready:getSessionPresenceCalibration(nodes).distributed_calibration_ready,logical_membership_state:{expected_cohort:cal.expectedCohort},transport_liveness_state:transport,observation_support:{window_ms:DETECTOR_V8.observationWindowMs,links:support},authoritative:true,source:'canonical_shared_rust_engine'} as PresenceEstimate;
  const sid=currentSession(nodes),seq=(decisionSequenceBySession.get(sid)??0)+1;decisionSequenceBySession.set(sid,seq);latestDecisionBySession.set(sid,{decision:{...result,decision_sequence:seq,decision_freshness_state:'FRESH'},receivedWallMs:now,sequence:seq});return{...result,decision_sequence:seq,decision_freshness_state:'FRESH'} as PresenceEstimate
}
export function selectAuthoritativePresence(nodes:Advertisement[],coordinatorNodeId:string|null,localNodeId:string|null,local:PresenceEstimate):PresenceEstimate{
  activateCalibrationScope(nodes,localNodeId);lastLocalNodeId=localNodeId;syncAuthoritativeCalibration(nodes,coordinatorNodeId,localNodeId);adoptCoordinatorIfNeeded(nodes,coordinatorNodeId,localNodeId);const sid=currentSession(nodes);
  if(!coordinatorNodeId)return fallback('coordinator_unavailable',cal.state,{transport_liveness_state:transportStates(nodes)});if(coordinatorNodeId===localNodeId)return local;
  const coordinator=nodes.find(n=>n.node_id===coordinatorNodeId);const rawDp=(coordinator?.control_plane as any)?.decision_meta_v10;const dp=rawDp?.schema==='DecisionMetaWireV2'?{schema:'DecisionMetaV10',sid:rawDp.s,coordinator_id:rawDp.n,cg:Number(rawDp.cg),g:Number(rawDp.g),cal_id:cal.artifact?.calibration_id??null,cal_hash:rawDp.ch,topology_hash:rawDp.t,seq:Number(rawDp.q),id:rawDp.i,digest:rawDp.d,prediction:rawDp.p,n:Number(rawDp.nn??0),l:Number(rawDp.ll??0),b:Number(rawDp.bb??0)}:rawDp;
  if(dp&&dp.schema==='DecisionMetaV10'&&dp.sid===sid&&dp.coordinator_id===coordinatorNodeId&&Number(dp.cg)===cal.coordinatorGeneration&&Number(dp.g)===cal.generation&&dp.cal_hash===cal.artifact?.calibration_hash&&dp.topology_hash===canonicalTopologyHash()&&dp.digest){const incomingSeq=Number(dp.seq??0),previous=latestDecisionBySession.get(sid);if(!previous||incomingSeq>=previous.sequence){const mirrored={prediction:String(dp.prediction??'INDETERMINATE'),human_confidence:0.5,evidence_quality:'CONTROL_META',fused_score:0,contributing_nodes:Number(dp.n??0),contributing_links:Number(dp.l??0),physical_baselines:Number(dp.b??0),reason:'DURABLE_DECISION_META_V10',calibration_state:cal.artifact?'READY':cal.state,calibration_id:dp.cal_id,calibration_hash:dp.cal_hash,calibration_generation:Number(dp.g??cal.generation),coordinator_generation:Number(dp.cg),topology_fingerprint:cal.topology,algorithm_version:DETECTOR_ALGORITHM,parameter_hash:DETECTOR_PARAMETER_HASH,window_id:String(dp.seq??''),authoritative:true,source:'decision_meta_v10',decision_sequence:incomingSeq,decision_id:dp.id,canonical_digest:dp.digest,decision_freshness_state:'FRESH'} as PresenceEstimate;latestDecisionBySession.set(sid,{decision:mirrored,receivedWallMs:Date.now(),sequence:incomingSeq});return mirrored}}
  const cached=latestDecisionBySession.get(sid);if(cached)return{...cached.decision,source:'durable_run_authority_ledger_v1',decision_freshness_state:decisionFreshness(cached.receivedWallMs),decision_age_ms:Date.now()-cached.receivedWallMs,authoritative:true} as PresenceEstimate;
  return fallback(cal.state==='STALE_AUTHORITY'?cal.reason:'WAIT_DECISION_EXPIRED',cal.state,{decision_freshness_state:'WAIT_DECISION',last_valid_decision_sequence:null,last_valid_decision_digest:null,transport_liveness_state:transportStates(nodes)})
}
