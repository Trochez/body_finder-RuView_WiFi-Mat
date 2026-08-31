import { Advertisement } from './autogeometry';
import BodyFinderNative from '../modules/body-finder-native';
import { DETECTOR_ALGORITHM, DETECTOR_PARAMETER_HASH, DETECTOR_V7 } from './detectorParameters';

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
};
type CalState={
  state:CalibrationState; generation:number; coordinator:string|null; topology:string|null; started:number; artifact:any|null;
  reason:string; expectedCohort:string[]; publicationSequence:number; lastAuthorityWallMs:number; coordinatorGeneration:number;
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
let cal:CalState={state:'UNCALIBRATED',generation:0,coordinator:null,topology:null,started:0,artifact:null,reason:'EMPTY_CAL_REQUIRED',expectedCohort:[],publicationSequence:0,lastAuthorityWallMs:0,coordinatorGeneration:0};

function pair(a:string,b:string){return a<b?`${a}::${b}`:`${b}::${a}`}
function sessionId(nodes:Advertisement[]){const counts=new Map<string,number>();for(const n of nodes){if(n.protocol_version!==2||!n.session_id)continue;counts.set(n.session_id,(counts.get(n.session_id)??0)+1)}return [...counts.entries()].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0]))[0]?.[0]??null}
function freshNodes(nodes:Advertisement[],sid:string|null){return nodes.filter(n=>n.protocol_version===2&&n.session_id===sid&&Boolean(n.node_id))}
function updateMembership(nodes:Advertisement[]):Membership|null{
  const sid=sessionId(nodes); if(!sid)return null; const now=Date.now();
  let m=membershipBySession.get(sid);
  if(!m){m={sessionId:sid,nodeIds:[],observed:new Set(),lastSeen:{},scores:{},unexpectedSince:{},coordinator:null,coordinatorGeneration:1,coordinatorMissingSince:null};membershipBySession.set(sid,m)}
  for(const n of freshNodes(nodes,sid)){const id=String(n.node_id);m.observed.add(id);m.lastSeen[id]=now;m.scores[id]=Number(n.coordinator_score??0)}
  if(m.nodeIds.length<3&&m.observed.size>=3){m.nodeIds=[...m.observed].sort().slice(0,3)}
  if(!m.nodeIds.length)m.nodeIds=[...m.observed].sort();
  const active=new Set(freshNodes(nodes,sid).map(n=>String(n.node_id)));
  for(const id of m.observed){if(!m.nodeIds.includes(id)){if(active.has(id)&&!m.unexpectedSince[id])m.unexpectedSince[id]=now;if(!active.has(id))delete m.unexpectedSince[id]}}
  if(!m.coordinator){
    const candidates=(m.nodeIds.length?m.nodeIds:[...active]).filter(id=>active.has(id));
    m.coordinator=candidates.sort((a,b)=>(m!.scores[b]??0)-(m!.scores[a]??0)||a.localeCompare(b))[0]??null;
  }
  if(m.coordinator&&!active.has(m.coordinator)){
    if(m.coordinatorMissingSince==null)m.coordinatorMissingSince=now;
    const absentFor=now-m.coordinatorMissingSince;
    const quorum=m.nodeIds.filter(id=>active.has(id));
    if(absentFor>=DETECTOR_V7.coordinatorFailoverGraceMs&&quorum.length>=2){
      const next=quorum.sort((a,b)=>(m!.scores[b]??0)-(m!.scores[a]??0)||a.localeCompare(b))[0]??null;
      if(next&&next!==m.coordinator){m.coordinator=next;m.coordinatorGeneration+=1}
      m.coordinatorMissingSince=null;
    }
  }else if(m.coordinator){m.coordinatorMissingSince=null}
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
  return Object.entries(m.unexpectedSince).filter(([,since])=>now-since>=DETECTOR_V7.membershipChangeGraceMs).map(([id])=>id).sort();
}
export function electStableCoordinator(nodes:Advertisement[],localNodeId:string|null){lastLocalNodeId=localNodeId;return updateMembership(nodes)?.coordinator??null}

function ingest(nodes:Advertisement[]):Link[]{const now=Date.now();for(const n of nodes){for(const r of n.ranges??[]){const v=Number(r.rssi_dbm);if(!Number.isFinite(v)||v>0||v<-126)continue;const observer=String(r.observer_node_id||n.node_id||'');const peer=String(r.peer_node_id||'');if(!observer||!peer)continue;const id=`${observer}::${peer}`;const source=Number((r as any).source_observation_monotonic_ns??r.monotonic_ns??0);if(source>0&&lastSource.get(id)===source)continue;if(source>0)lastSource.set(id,source);const q=history.get(id)??[];q.push({receive_wall_ms:now,source_monotonic_ns:source>0?source:null,rssi_dbm:v});history.set(id,q.filter(s=>now-s.receive_wall_ms<=HISTORY_MS).slice(-240));}}return [...history.entries()].map(([id,samples])=>{const [observer,peer]=id.split('::');return{link_id:id,observer_node_id:observer,peer_node_id:peer,samples}}).sort((a,b)=>a.link_id.localeCompare(b.link_id))}
function expectedLinks(links:Link[],cohort:string[]){const ids=new Set<string>();for(const a of cohort)for(const b of cohort)if(a!==b)ids.add(`${a}::${b}`);return links.filter(l=>ids.has(l.link_id))}
function topology(links:Link[],cohort:string[]){const live=expectedLinks(links,cohort).filter(l=>l.samples.length&&Date.now()-l.samples.at(-1)!.receive_wall_ms<DETECTOR_V7.transportEvidenceFreshMs);const nodes=new Set(live.map(l=>l.observer_node_id));const baselines=new Set(live.map(l=>pair(l.observer_node_id,l.peer_node_id)));return{ok:cohort.length===3&&nodes.size>=3&&live.length>=6&&baselines.size>=3,fingerprint:cohortFingerprint(cohort),links:live,nodes:nodes.size,baselines:baselines.size}}
function native(input:any){try{const out=JSON.parse(BodyFinderNative.evaluateHumanPresenceJson(JSON.stringify(input)));if(out?.error)throw new Error(String(out.error));return out}catch(e:any){return{error:String(e?.message??e)}}}
function publicationFrom(nodes:Advertisement[],coordinatorNodeId:string|null){const coordinator=nodes.find(n=>n.node_id===coordinatorNodeId);const pg=(coordinator?.published_geometry as any);return pg?.authoritative_presence?.calibration_publication_v6??pg?.calibration_publication_v6??null}
function currentSession(nodes:Advertisement[]){return sessionId(nodes)??'body-finder-lab'}
function decisionFreshness(receivedWallMs:number){const age=Math.max(0,Date.now()-receivedWallMs);return age<=DECISION_FRESH_MS?'FRESH':age<=DECISION_EXPIRED_MS?'STALE':'EXPIRED'}
function fallback(reason:string,state:CalibrationState=cal.state,extra:Record<string,unknown>={}):PresenceEstimate{return{prediction:'INDETERMINATE',human_confidence:0.5,evidence_quality:'LOW',fused_score:0,contributing_nodes:0,contributing_links:0,physical_baselines:0,reason,calibration_state:state,calibration_id:cal.artifact?.calibration_id??null,calibration_hash:cal.artifact?.calibration_hash??null,algorithm_version:DETECTOR_ALGORITHM,parameter_hash:DETECTOR_PARAMETER_HASH,window_id:String(Math.floor(Date.now()/2000)*2000),authoritative:false,source:'diagnostic_fail_closed',logical_membership_state:{expected_cohort:cal.expectedCohort},transport_liveness_state:extra.transport_liveness_state??[],...extra}}

function syncAuthoritativeCalibration(nodes:Advertisement[],coordinatorNodeId:string|null,localNodeId:string|null){
  lastLocalNodeId=localNodeId;if(!coordinatorNodeId||coordinatorNodeId===localNodeId)return;const p=publicationFrom(nodes,coordinatorNodeId),now=Date.now();
  if(p?.schema==='CalibrationPublicationV6'&&p?.detector_parameter_hash===DETECTOR_PARAMETER_HASH&&p?.artifact?.calibration_hash===p?.calibration_hash){
    const incomingCg=Number(p.coordinator_generation??0),incomingCal=Number(p.calibration_generation??0),incomingSeq=Number(p.publication_sequence??0);
    const sameOrNewer=incomingCg>cal.coordinatorGeneration||(incomingCg===cal.coordinatorGeneration&&incomingCal>=cal.generation);
    const ordered=incomingCg>cal.coordinatorGeneration||incomingSeq>=cal.publicationSequence;
    if(sameOrNewer&&ordered){cal={...cal,state:'READY',generation:incomingCal,coordinator:coordinatorNodeId,topology:String(p.topology_fingerprint),artifact:p.artifact,reason:'AUTHORITATIVE_CALIBRATION_MIRRORED',expectedCohort:Array.isArray(p.expected_cohort)?p.expected_cohort.map(String).sort():cal.expectedCohort,publicationSequence:incomingSeq,lastAuthorityWallMs:now,coordinatorGeneration:incomingCg}}
  }else if(cal.artifact&&cal.lastAuthorityWallMs&&now-cal.lastAuthorityWallMs>DETECTOR_V7.authorityPublicationLeaseMs){cal={...cal,state:'STALE_AUTHORITY',reason:'AUTHORITY_PUBLICATION_LEASE_EXPIRED_CALIBRATION_PRESERVED'}}
}
function adoptCoordinatorIfNeeded(nodes:Advertisement[],coordinatorNodeId:string|null,localNodeId:string|null){
  if(!coordinatorNodeId||coordinatorNodeId!==localNodeId||!cal.artifact)return;const m=updateMembership(nodes);if(!m)return;
  if(cal.coordinator!==coordinatorNodeId||cal.coordinatorGeneration<m.coordinatorGeneration){cal={...cal,state:'READY',coordinator:coordinatorNodeId,coordinatorGeneration:m.coordinatorGeneration,publicationSequence:0,lastAuthorityWallMs:Date.now(),reason:'AUTHORITY_FAILOVER_ADOPTED_EXISTING_FROZEN_CALIBRATION'}}
}
function exactAck(node:Advertisement,id:string){
  if(!cal.artifact)return false;if(id===cal.coordinator)return true;if(id===lastLocalNodeId&&cal.expectedCohort.includes(id))return true;
  const a=(node.control_plane as any)?.calibration_ack_v6;
  return Boolean(a&&a.schema==='CalibrationAckV6'&&a.node_id===id&&a.calibration_id===cal.artifact.calibration_id&&a.calibration_hash===cal.artifact.calibration_hash&&Number(a.calibration_generation)===cal.generation&&Number(a.coordinator_generation)===cal.coordinatorGeneration);
}
function peerAckMatrix(nodes:Advertisement[]){
  return cal.expectedCohort.map(id=>{const n=nodes.find(x=>x.node_id===id);return{node_id:id,acknowledged:Boolean(n&&exactAck(n,id))||id===cal.coordinator||id===lastLocalNodeId,calibration_id:cal.artifact?.calibration_id??null,calibration_hash:cal.artifact?.calibration_hash??null,calibration_generation:cal.generation,coordinator_generation:cal.coordinatorGeneration}})
}

export function beginSessionPresenceCalibration(nodes:Advertisement[],coordinatorNodeId:string|null,localNodeId:string|null){
  lastLocalNodeId=localNodeId;const links=ingest(nodes),cohort=stableCohort(nodes),t=topology(links,cohort);
  if(!coordinatorNodeId||coordinatorNodeId!==localNodeId){syncAuthoritativeCalibration(nodes,coordinatorNodeId,localNodeId);if(cal.artifact)return cal;cal={...cal,state:'WAIT_COORDINATOR',coordinator:coordinatorNodeId,reason:'CALIBRATION_MUST_BE_STARTED_ON_ELECTED_COORDINATOR'};return cal}
  if(cohort.length!==3||!t.ok){cal={...cal,state:'INVALID',coordinator:coordinatorNodeId,reason:'CALIBRATION_REQUIRES_3_NODES_6_LINKS_3_BASELINES'};return cal}
  const m=updateMembership(nodes);
  cal={state:'CALIBRATING',generation:cal.generation+1,coordinator:coordinatorNodeId,topology:t.fingerprint,started:Date.now(),artifact:null,reason:'COLLECTING_SYNCHRONIZED_EMPTY_BASELINE',expectedCohort:cohort,publicationSequence:0,lastAuthorityWallMs:Date.now(),coordinatorGeneration:m?.coordinatorGeneration??Math.max(1,cal.coordinatorGeneration)};
  return cal
}
export function getSessionPresenceCalibration(nodes:Advertisement[]=[]){
  const matrix=peerAckMatrix(nodes),expected=cal.expectedCohort.length||3,ackCount=matrix.filter(x=>x.acknowledged).length;
  return{state:cal.state,generation:cal.generation,calibration_generation:cal.generation,coordinator_generation:cal.coordinatorGeneration,coordinator_node_id:cal.coordinator,topology_fingerprint:cal.topology,expected_cohort:cal.expectedCohort,started_wall_ms:cal.started,calibration_id:cal.artifact?.calibration_id??null,calibration_hash:cal.artifact?.calibration_hash??null,reason:cal.reason,publication_sequence:cal.publicationSequence,authority_lease_age_ms:cal.lastAuthorityWallMs?Date.now()-cal.lastAuthorityWallMs:null,peer_ack_matrix:matrix,peer_ack_count:ackCount,distributed_calibration_ready:cal.state==='READY'&&expected===3&&ackCount===3,logical_membership_state:{cohort:cal.expectedCohort,confirmed_change:confirmedMembershipChanges(nodes)},transport_liveness_state:transportStates(nodes)}
}
export function getCalibrationPublication(localNodeId:string|null){
  if(!cal.artifact||cal.coordinator!==localNodeId||cal.state!=='READY')return null;cal.publicationSequence+=1;cal.lastAuthorityWallMs=Date.now();
  return{schema:'CalibrationPublicationV6',session_id:cal.artifact.session_id,coordinator_id:cal.coordinator,coordinator_generation:cal.coordinatorGeneration,calibration_generation:cal.generation,calibration_id:cal.artifact.calibration_id,calibration_hash:cal.artifact.calibration_hash,topology_fingerprint:cal.topology,expected_cohort:cal.expectedCohort,publication_sequence:cal.publicationSequence,publication_wall_ms:Date.now(),lease_timeout_ms:DETECTOR_V7.authorityPublicationLeaseMs,detector_parameter_hash:DETECTOR_PARAMETER_HASH,state:'READY',reason:cal.reason,artifact:cal.artifact}
}
export function getControlPlanePublication(nodes:Advertisement[],coordinatorNodeId:string|null,localNodeId:string|null){
  lastLocalNodeId=localNodeId;syncAuthoritativeCalibration(nodes,coordinatorNodeId,localNodeId);adoptCoordinatorIfNeeded(nodes,coordinatorNodeId,localNodeId);
  const sid=currentSession(nodes);
  const ack=cal.artifact&&localNodeId&&cal.expectedCohort.includes(localNodeId)?{schema:'CalibrationAckV6',session_id:cal.artifact.session_id,node_id:localNodeId,coordinator_id:cal.coordinator,coordinator_generation:cal.coordinatorGeneration,calibration_generation:cal.generation,calibration_id:cal.artifact.calibration_id,calibration_hash:cal.artifact.calibration_hash,ack_wall_ms:Date.now()}:null;
  const cached=latestDecisionBySession.get(sid);
  const decisionPublication=cached&&coordinatorNodeId===localNodeId&&cached.decision.authoritative&&cached.decision.canonical_digest?{schema:'DecisionPublicationV7',session_id:sid,coordinator_id:coordinatorNodeId,coordinator_generation:cal.coordinatorGeneration,calibration_id:cached.decision.calibration_id??cal.artifact?.calibration_id??null,calibration_hash:cached.decision.calibration_hash??cal.artifact?.calibration_hash??null,calibration_generation:cached.decision.calibration_generation??cal.generation,topology_fingerprint:cached.decision.topology_fingerprint??cal.topology,detector_algorithm:DETECTOR_ALGORITHM,detector_parameter_hash:DETECTOR_PARAMETER_HASH,decision_sequence:cached.sequence,decision_id:cached.decision.decision_id,canonical_digest:cached.decision.canonical_digest,window_id:cached.decision.window_id,publication_wall_ms:Date.now(),source_decision_wall_ms:cached.receivedWallMs,freshness_state:decisionFreshness(cached.receivedWallMs),fresh_ms:DECISION_FRESH_MS,expiry_ms:DECISION_EXPIRED_MS,decision:cached.decision}:null;
  const decisionAck=cached&&localNodeId?{schema:'DecisionAckV7',session_id:sid,node_id:localNodeId,coordinator_id:coordinatorNodeId,coordinator_generation:cal.coordinatorGeneration,decision_sequence:cached.sequence,decision_id:cached.decision.decision_id??null,canonical_digest:cached.decision.canonical_digest??null,ack_wall_ms:Date.now()}:null;
  return{schema:'BodyFinderControlPlaneV7',session_id:sid,node_id:localNodeId,logical_membership_state:{expected_cohort:stableCohort(nodes),transport_liveness_state:transportStates(nodes)},calibration_ack_v6:ack,decision_publication_v7:decisionPublication,decision_ack_v7:decisionAck}
}

function maybeFreeze(nodes:Advertisement[],coordinatorNodeId:string|null,localNodeId:string|null,links:Link[]){
  if(cal.state!=='CALIBRATING'||coordinatorNodeId!==localNodeId)return;
  if(Date.now()-cal.started>DETECTOR_V7.calibrationTimeoutMs){cal={...cal,state:'INVALID',reason:'CALIBRATION_INSUFFICIENT_SUPPORT'};return}
  const t=topology(links,cal.expectedCohort);if(!t.ok)return;
  const selected=t.links.map(l=>({...l,samples:l.samples.filter(s=>s.receive_wall_ms>=cal.started)}));
  const starts=selected.map(l=>l.samples[0]?.receive_wall_ms??Infinity),ends=selected.map(l=>l.samples.at(-1)?.receive_wall_ms??-Infinity);const overlap=Math.min(...ends)-Math.max(...starts);
  if(selected.some(l=>l.samples.length<DETECTOR_V7.calibrationMinSamplesPerLink)||overlap<DETECTOR_V7.calibrationMinOverlapMs)return;
  const session=currentSession(nodes),calibrationId=`cal-d207-${cal.generation}-${coordinatorNodeId?.slice(-8)??'none'}-${cal.started}`;
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
  const now=Date.now(),start=Math.max(Number(cal.artifact.frozen_wall_ms)+250,now-DETECTOR_V7.observationWindowMs);
  const obs=expectedLinks(links,cal.expectedCohort).map(l=>({...l,samples:l.samples.filter(s=>s.receive_wall_ms>=start).slice(-240)}));
  const support=obs.map(l=>({link_id:l.link_id,actual_samples:l.samples.length,min_samples:DETECTOR_V7.observationMinSamplesPerLink,first_receive_wall_ms:l.samples[0]?.receive_wall_ms??null,last_receive_wall_ms:l.samples.at(-1)?.receive_wall_ms??null}));
  const insufficient=support.filter(s=>s.actual_samples<DETECTOR_V7.observationMinSamplesPerLink);
  if(obs.length!==6||insufficient.length)return fallback('OBSERVATION_SUPPORT_INCOMPLETE_DEADLINE_NOT_YET_ADMISSIBLE','READY',{observation_support:{window_ms:DETECTOR_V7.observationWindowMs,links:support,insufficient_links:insufficient.map(x=>x.link_id)},transport_liveness_state:transport});
  const input={operation:'INFER',session_id:currentSession(nodes),window_id:String(Math.floor(now/2000)*2000),window_start_wall_ms:Math.min(...obs.flatMap(l=>l.samples.map(s=>s.receive_wall_ms)),now),window_end_wall_ms:now,detector_parameter_hash:DETECTOR_PARAMETER_HASH,calibration:cal.artifact,acquisition_health:{environment_valid:true,acquisition_valid:true},links:obs};
  const out=native(input);if(out.error)return fallback(`canonical_engine_error:${out.error}`,'READY',{observation_support:{links:support},transport_liveness_state:transport});
  const publication=getCalibrationPublication(localNodeId);
  const result={...out,calibration_state:out.calibration_state??'READY',calibration_id:cal.artifact.calibration_id,calibration_hash:cal.artifact.calibration_hash,calibration_generation:cal.generation,coordinator_generation:cal.coordinatorGeneration,topology_fingerprint:cal.topology,expected_cohort:cal.expectedCohort,calibration_publication_v6:publication,peer_ack_matrix:peerAckMatrix(nodes),distributed_calibration_ready:getSessionPresenceCalibration(nodes).distributed_calibration_ready,logical_membership_state:{expected_cohort:cal.expectedCohort},transport_liveness_state:transport,observation_support:{window_ms:DETECTOR_V7.observationWindowMs,links:support},authoritative:true,source:'canonical_shared_rust_engine'} as PresenceEstimate;
  const sid=currentSession(nodes),seq=(decisionSequenceBySession.get(sid)??0)+1;decisionSequenceBySession.set(sid,seq);latestDecisionBySession.set(sid,{decision:{...result,decision_sequence:seq,decision_freshness_state:'FRESH'},receivedWallMs:now,sequence:seq});return{...result,decision_sequence:seq,decision_freshness_state:'FRESH'} as PresenceEstimate
}
export function selectAuthoritativePresence(nodes:Advertisement[],coordinatorNodeId:string|null,localNodeId:string|null,local:PresenceEstimate):PresenceEstimate{
  lastLocalNodeId=localNodeId;syncAuthoritativeCalibration(nodes,coordinatorNodeId,localNodeId);adoptCoordinatorIfNeeded(nodes,coordinatorNodeId,localNodeId);const sid=currentSession(nodes);
  if(!coordinatorNodeId)return fallback('coordinator_unavailable',cal.state,{transport_liveness_state:transportStates(nodes)});
  if(coordinatorNodeId===localNodeId)return local
  const coordinator=nodes.find(n=>n.node_id===coordinatorNodeId);const dp=(coordinator?.control_plane as any)?.decision_publication_v7;
  if(dp&&dp.schema==='DecisionPublicationV7'&&dp.session_id===sid&&dp.coordinator_id===coordinatorNodeId&&Number(dp.coordinator_generation)===cal.coordinatorGeneration&&dp.detector_algorithm===DETECTOR_ALGORITHM&&dp.detector_parameter_hash===DETECTOR_PARAMETER_HASH&&dp.calibration_hash===cal.artifact?.calibration_hash&&dp.canonical_digest&&dp.decision?.canonical_digest===dp.canonical_digest&&dp.decision?.decision_id===dp.decision_id){
    const incomingSeq=Number(dp.decision_sequence??0),previous=latestDecisionBySession.get(sid);
    if(!previous||incomingSeq>=previous.sequence){const mirrored={...dp.decision,calibration_state:cal.artifact?'READY':dp.decision.calibration_state,source:'decision_control_plane_v7',decision_sequence:incomingSeq,decision_freshness_state:'FRESH'} as PresenceEstimate;latestDecisionBySession.set(sid,{decision:mirrored,receivedWallMs:Date.now(),sequence:incomingSeq});return mirrored}
  }
  const published=(coordinator?.published_geometry as any)?.authoritative_presence;
  if(published&&published.authoritative===true&&published.algorithm_version===DETECTOR_ALGORITHM&&published.parameter_hash===DETECTOR_PARAMETER_HASH&&published.canonical_digest&&published.calibration_hash===cal.artifact?.calibration_hash){
    const previous=latestDecisionBySession.get(sid),seq=previous?.sequence??0;const mirrored={...published,calibration_state:cal.artifact?'READY':published.calibration_state,source:'legacy_geometry_decision_fallback',decision_sequence:seq,decision_freshness_state:'FRESH'} as PresenceEstimate;latestDecisionBySession.set(sid,{decision:mirrored,receivedWallMs:Date.now(),sequence:seq});return mirrored
  }
  const cached=latestDecisionBySession.get(sid);if(cached&&decisionFreshness(cached.receivedWallMs)!=='EXPIRED')return{...cached.decision,source:'cached_decision_publication_v7',decision_freshness_state:decisionFreshness(cached.receivedWallMs),decision_age_ms:Date.now()-cached.receivedWallMs} as PresenceEstimate;
  return fallback(cal.state==='STALE_AUTHORITY'?cal.reason:'WAIT_DECISION_EXPIRED',cal.state,{decision_freshness_state:cached?'EXPIRED':'WAIT_DECISION',last_valid_decision_sequence:cached?.sequence??null,last_valid_decision_digest:cached?.decision.canonical_digest??null,transport_liveness_state:transportStates(nodes)})
}
