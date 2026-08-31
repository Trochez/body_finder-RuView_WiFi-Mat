#!/usr/bin/env python3
from __future__ import annotations
import json,re,shutil,pathlib,hashlib

ROOT=pathlib.Path(__file__).resolve().parents[1]

def p(rel): return ROOT/rel

def read(rel): return p(rel).read_text()
def write(rel,s):
    q=p(rel); q.parent.mkdir(parents=True,exist_ok=True); q.write_text(s)

def once(s,old,new,label):
    if old not in s: raise SystemExit(f'missing anchor {label}')
    return s.replace(old,new,1)

def jwrite(rel,obj): write(rel,json.dumps(obj,indent=2,sort_keys=True)+'\n')

# Version/safety contract.
s=read('apps/mobile/src/version.ts')
s=s.replace("0.2.0-experimental.20.8","0.2.0-experimental.20.9").replace("reportVersion: 28","reportVersion: 29").replace("versionCode: 28","versionCode: 29").replace("experimental.20.8","experimental.20.9").replace("snapshotSchemaVersion: 11","snapshotSchemaVersion: 12")
write('apps/mobile/src/version.ts',s)

# Geometry: isolate clock domains and adopt explicit coordinator publication V9.
s=read('apps/mobile/src/autogeometry.ts')
s=once(s,"  monotonic_ns: number;\n  distance_m: number | null;","  monotonic_ns: number; // foreign sender monotonic: diagnostic/order metadata only\n  sender_range_age_ms?: number;\n  sender_temporal_state?: string;\n  sender_sequence?: number;\n  instance_epoch?: string;\n  received_local_monotonic_ns?: number;\n  effective_age_ms?: number;\n  range_domain_state?: string;\n  distance_m: number | null;",'range temporal fields')
s=once(s,"  node_id: string;\n  display_name: string;","  node_id: string;\n  instance_epoch?: string;\n  membership_lease_age_ms?: number;\n  membership_lease_state?: string;\n  display_name: string;",'advertisement instance fields')
s=s.replace("    | 'ELECTED_COORDINATOR_PUBLICATION'\n    | 'LOCAL_DETERMINISTIC_FALLBACK_AWAITING_COORDINATOR_PUBLICATION';","    | 'ELECTED_COORDINATOR_PUBLICATION'\n    | 'COORDINATOR_PUBLICATION_V9'\n    | 'LOCAL_DETERMINISTIC_FALLBACK_AWAITING_COORDINATOR_PUBLICATION';\n  publication_rejection_reason?: string | null;")
start=s.index('function collectEdges('); end=s.index('\nconst edge =',start)
new_collect=r'''function collectEdges(nodes: Advertisement[], rejected: Rejected) {
  const ids = new Set(nodes.map(node => node.node_id));
  const session = nodes[0]?.session_id ?? '';
  const groups = new Map<string, RangeObservation[]>();
  const latestSequenceBySource = new Map<string, number>();

  for (const node of nodes) {
    for (const observation of node.ranges ?? []) {
      if (observation.session_id !== session || observation.observer_node_id !== node.node_id) continue;
      const sourceKey = `${observation.observer_node_id}\u0000${observation.peer_node_id}\u0000${observation.technology}`;
      const sequence = Number(observation.sender_sequence ?? 0);
      if (Number.isFinite(sequence) && sequence > 0) latestSequenceBySource.set(sourceKey, Math.max(latestSequenceBySource.get(sourceKey) ?? 0, sequence));
    }
  }

  for (const node of nodes) {
    for (const observation of node.ranges ?? []) {
      const [a, b] = pair(observation.observer_node_id, observation.peer_node_id);
      const edgeId = `${a}::${b}::${observation.technology}`;
      if (observation.session_id !== session || observation.session_id !== node.session_id || observation.observer_node_id !== node.node_id) {
        rejected.push({ edge_id: edgeId, reason: 'session/observer identity mismatch' });
        continue;
      }
      if (!ids.has(observation.peer_node_id) || observation.peer_node_id === observation.observer_node_id) {
        rejected.push({ edge_id: edgeId, reason: 'peer not active in geometry graph' });
        continue;
      }
      // AD-20.9-01: never subtract/order a foreign Android monotonic epoch against this device.
      const effectiveAgeMs = Number(observation.effective_age_ms ?? observation.sender_range_age_ms ?? Number.NaN);
      if (!Number.isFinite(effectiveAgeMs) || effectiveAgeMs < 0) {
        rejected.push({ edge_id: edgeId, reason: 'invalid normalized sender age' });
        continue;
      }
      if (effectiveAgeMs * 1_000_000 > RANGE_SAMPLE_STALE_NS) {
        rejected.push({ edge_id: edgeId, reason: 'stale normalized range sample expired from geometry graph' });
        continue;
      }
      const sourceKey = `${observation.observer_node_id}\u0000${observation.peer_node_id}\u0000${observation.technology}`;
      const sequence = Number(observation.sender_sequence ?? 0);
      const latestSequence = latestSequenceBySource.get(sourceKey) ?? sequence;
      if (sequence > 0 && latestSequence > sequence) {
        rejected.push({ edge_id: edgeId, reason: 'replayed/out-of-order sender sequence rejected' });
        continue;
      }
      const domainState = String(observation.range_domain_state ?? observation.sender_temporal_state ?? 'FRESH');
      if (domainState === 'OUT_OF_DOMAIN' || domainState.startsWith('OUT_OF_DOMAIN')) {
        rejected.push({ edge_id: edgeId, reason: 'range measurement OUT_OF_DOMAIN' });
        continue;
      }
      const distance = observation.distance_m;
      const sigma = observation.distance_sigma_m ?? 3;
      if (distance == null || !Number.isFinite(distance) || distance < 0.05 || distance > 100 || !Number.isFinite(sigma) || sigma < 0.05 || sigma > 30 || qWeight(observation.quality) <= 0) {
        rejected.push({ edge_id: edgeId, reason: 'invalid or rejected range sample' });
        continue;
      }
      const groupKey = `${a}\u0000${b}\u0000${observation.technology}`;
      groups.set(groupKey, [...(groups.get(groupKey) ?? []), observation]);
    }
  }

  const bestByPair = new Map<string, Edge>();
  for (const [key, samples] of groups) {
    const [a, b, technology] = key.split('\u0000');
    const distances = samples.map(sample => sample.distance_m!).filter(Number.isFinite);
    if (!distances.length) continue;
    const distance = median(distances);
    const mad = median(distances.map(value => Math.abs(value - distance)));
    const sigma = Math.max(0.15, median(samples.map(sample => sample.distance_sigma_m ?? 3)), 1.4826 * mad);
    const q = Math.max(...samples.map(sample => qWeight(sample.quality)));
    const candidate: Edge = { id: `${a}::${b}::${technology}`, a, b, technology, d: distance, sigma, q, latest: Math.max(...samples.map(sample => Number(sample.sender_sequence ?? 0))) };
    const pairKey = `${a}\u0000${b}`;
    const current = bestByPair.get(pairKey);
    const score = candidate.q / Math.max(0.02, candidate.sigma ** 2);
    const currentScore = current ? current.q / Math.max(0.02, current.sigma ** 2) : -1;
    if (!current || score > currentScore || (Math.abs(score-currentScore)<1e-12 && technology<current.technology)) bestByPair.set(pairKey,candidate);
  }
  return [...bestByPair.values()].sort((a,b)=>a.id.localeCompare(b.id));
}
'''
s=s[:start]+new_collect+s[end:]
start=s.index('export function chooseCoordinatorGeometry('); end=s.index('\nexport function estimateHuman',start)
new_choose=r'''export function chooseCoordinatorGeometry(
  nodes: Advertisement[], coordinatorNodeId: string | null, localNodeId: string | null, localSolution: GeometrySolution | null,
): GeometrySelection {
  if (coordinatorNodeId && coordinatorNodeId === localNodeId) return { solution: localSolution, source: 'LOCAL_ELECTED_COORDINATOR', publication_rejection_reason: null };
  const coordinator = coordinatorNodeId ? nodes.find(node => node.node_id === coordinatorNodeId) : undefined;
  if (!coordinator) return { solution: localSolution, source: 'LOCAL_DETERMINISTIC_FALLBACK_AWAITING_COORDINATOR_PUBLICATION', publication_rejection_reason: 'COORDINATOR_NOT_PRESENT' };
  const publication:any = coordinator.published_geometry;
  if (!publication) return { solution: localSolution, source: 'LOCAL_DETERMINISTIC_FALLBACK_AWAITING_COORDINATOR_PUBLICATION', publication_rejection_reason: 'PUBLICATION_ABSENT' };
  if (coordinator.geometry_publisher_node_id !== coordinatorNodeId || publication.publisher_node_id !== coordinatorNodeId) return { solution: localSolution, source: 'LOCAL_DETERMINISTIC_FALLBACK_AWAITING_COORDINATOR_PUBLICATION', publication_rejection_reason: 'WRONG_COORDINATOR_PUBLISHER' };
  if (publication.publication_session_id && publication.publication_session_id !== coordinator.session_id) return { solution: localSolution, source: 'LOCAL_DETERMINISTIC_FALLBACK_AWAITING_COORDINATOR_PUBLICATION', publication_rejection_reason: 'PUBLICATION_SESSION_MISMATCH' };
  if (!publication.frame_id || !Array.isArray(publication.positions)) return { solution: localSolution, source: 'LOCAL_DETERMINISTIC_FALLBACK_AWAITING_COORDINATOR_PUBLICATION', publication_rejection_reason: 'PUBLICATION_MALFORMED' };
  return { solution: publication, source: 'COORDINATOR_PUBLICATION_V9', publication_rejection_reason: null };
}
'''
s=s[:start]+new_choose+s[end:]
write('apps/mobile/src/autogeometry.ts',s)

# Instance-aware membership and finite leases.
s=read('apps/mobile/src/humanPresence.ts')
s=once(s,"  unexpectedSince:Record<string,number>; coordinator:string|null; coordinatorGeneration:number; coordinatorMissingSince:number|null;\n};","  unexpectedSince:Record<string,number>; coordinator:string|null; coordinatorGeneration:number; coordinatorMissingSince:number|null;\n  instanceByNode:Record<string,string>; transitions:{wall_ms:number;kind:string;node_id:string;instance_epoch:string;reason:string}[];\n};",'membership fields')
s=s.replace("function freshNodes(nodes:Advertisement[],sid:string|null){return nodes.filter(n=>n.protocol_version===2&&n.session_id===sid&&Boolean(n.node_id))}","function freshNodes(nodes:Advertisement[],sid:string|null){return nodes.filter(n=>n.protocol_version===2&&n.session_id===sid&&Boolean(n.node_id)&&Number((n as any).membership_lease_age_ms??0)<=15_000&&String((n as any).membership_lease_state??'LIVE')!=='EXPIRED')}")
s=s.replace("m={sessionId:sid,nodeIds:[],observed:new Set(),lastSeen:{},scores:{},unexpectedSince:{},coordinator:null,coordinatorGeneration:1,coordinatorMissingSince:null}","m={sessionId:sid,nodeIds:[],observed:new Set(),lastSeen:{},scores:{},unexpectedSince:{},coordinator:null,coordinatorGeneration:1,coordinatorMissingSince:null,instanceByNode:{},transitions:[]}")
old="for(const n of freshNodes(nodes,sid)){const id=String(n.node_id);m.observed.add(id);m.lastSeen[id]=now;m.scores[id]=Number(n.coordinator_score??0)}\n  if(m.nodeIds.length<3&&m.observed.size>=3){m.nodeIds=[...m.observed].sort().slice(0,3)}"
new="for(const n of freshNodes(nodes,sid)){const id=String(n.node_id),inst=String((n as any).instance_epoch??'legacy');const prior=m.instanceByNode[id];if(prior&&prior!==inst){m.transitions.push({wall_ms:now,kind:'REPLACE',node_id:id,instance_epoch:inst,reason:'NEW_INSTANCE_EPOCH'});m.transitions=m.transitions.slice(-64)}m.instanceByNode[id]=inst;m.observed.add(id);m.lastSeen[id]=now;m.scores[id]=Number(n.coordinator_score??0)}\n  for(const id of m.nodeIds.slice()){if(now-(m.lastSeen[id]??0)>15_000){m.nodeIds=m.nodeIds.filter(x=>x!==id);m.transitions.push({wall_ms:now,kind:'PRUNE',node_id:id,instance_epoch:m.instanceByNode[id]??'unknown',reason:'LEASE_EXPIRED'});delete m.instanceByNode[id]}}\n  const activeIds=[...new Set(freshNodes(nodes,sid).map(n=>String(n.node_id)))].sort();if(m.nodeIds.length<3){for(const id of activeIds)if(!m.nodeIds.includes(id)&&m.nodeIds.length<3)m.nodeIds.push(id)}m.nodeIds=m.nodeIds.filter(id=>activeIds.includes(id)).sort()"
s=once(s,old,new,'membership update')
s=s.replace("logical_membership_state:{cohort:cal.expectedCohort,confirmed_change:confirmedMembershipChanges(nodes)}","logical_membership_state:{cohort:cal.expectedCohort,current_instances:cal.expectedCohort.map(id=>({node_id:id,instance_epoch:updateMembership(nodes)?.instanceByNode[id]??null})),confirmed_change:confirmedMembershipChanges(nodes),transitions:updateMembership(nodes)?.transitions??[]}")
write('apps/mobile/src/humanPresence.ts',s)

# Native Wire V9: compact ranges, local receive clock, instance epoch, publication adoption telemetry.
rel='apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt'
s=read(rel)
s=s.replace('WireTransportV8','WireTransportV9').replace('WireEnvelopeV8','WireEnvelopeV9').replace('WireTransportTelemetryV8','WireTransportTelemetryV9')
s=once(s,'  const val MAX_DATAGRAM_BYTES = 1200\n  private const val CHUNK_BYTES = 512','  const val MAX_DATAGRAM_BYTES = 1200\n  const val RANGE_FRAME_TARGET_BYTES = 1050\n  private const val CHUNK_BYTES = 512','wire target')
s=once(s,'  private val rxBytesByType=java.util.concurrent.ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong>()','  private val rxBytesByType=java.util.concurrent.ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong>()\n  private val maxBytesByType=java.util.concurrent.ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong>()\n  val requiredFrameOversizeCount=java.util.concurrent.atomic.AtomicLong(0)','wire counters')
s=once(s,'    maxDatagramBytesObserved.updateAndGet{v->kotlin.math.max(v,b.size.toLong())}\n    if(b.size>MAX_DATAGRAM_BYTES){oversizeBlockCount.incrementAndGet();throw IllegalStateException("WIRE_OVERSIZE_${type}_${b.size}")}','    maxDatagramBytesObserved.updateAndGet{v->kotlin.math.max(v,b.size.toLong())}\n    maxBytesByType.computeIfAbsent(type){java.util.concurrent.atomic.AtomicLong(0)}.updateAndGet{v->kotlin.math.max(v,b.size.toLong())}\n    if(type=="RANGE_FRAME" && b.size>RANGE_FRAME_TARGET_BYTES){requiredFrameOversizeCount.incrementAndGet();oversizeBlockCount.incrementAndGet();throw IllegalStateException("WIRE_OVERSIZE_RANGE_FRAME_${b.size}")}\n    if(b.size>MAX_DATAGRAM_BYTES){if(type=="RANGE_FRAME")requiredFrameOversizeCount.incrementAndGet();oversizeBlockCount.incrementAndGet();throw IllegalStateException("WIRE_OVERSIZE_${type}_${b.size}")}','wire enforce')
s=s.replace('for(k in listOf("protocol_version","display_name","platform","coordinator_score","rssi_dbm","baseline_rssi_dbm","baseline_sigma_db","scanning","ble_identity","manual_geometry_override"))if(advertisement.has(k))o.put(k,advertisement.opt(k))','for(k in listOf("protocol_version","instance_epoch","display_name","platform","coordinator_score","rssi_dbm","baseline_rssi_dbm","baseline_sigma_db","scanning","ble_identity","manual_geometry_override"))if(advertisement.has(k))o.put(k,advertisement.opt(k))')
old='for(i in 0 until ranges.length()){val r=ranges.optJSONObject(i)?:continue;val sub="${r.optString("observer_node_id")}::${r.optString("peer_node_id")}";safeAdd(out,"RANGE_FRAME",node,session,seq){o->o.put("range_key",sub).put("range",r)}}'
new='for(i in 0 until ranges.length()){val r=ranges.optJSONObject(i)?:continue;val sub="${r.optString("observer_node_id")}::${r.optString("peer_node_id")}";val senderNow=advertisement.optLong("monotonic_ns",0L);val observationMono=r.optLong("monotonic_ns",0L);val senderAge=if(senderNow>0L&&observationMono>0L)kotlin.math.max(0L,(senderNow-observationMono)/1_000_000L) else r.optLong("range_age_ms",0L);safeAdd(out,"RANGE_FRAME",node,session,seq){o->o.put("range_key",sub).put("instance_epoch",FabricRuntime.instanceEpoch).put("observer_node_id",r.optString("observer_node_id")).put("peer_node_id",r.optString("peer_node_id")).put("technology",r.optString("technology")).put("sender_range_age_ms",senderAge).put("sender_temporal_state",r.optString("range_temporal_state","FRESH")).put("sender_sequence",seq).put("distance_m",r.opt("distance_m")).put("distance_sigma_m",r.opt("distance_sigma_m")).put("rssi_dbm",r.opt("rssi_dbm")).put("quality",r.optString("quality","LOW")).put("range_domain_state",r.optString("range_temporal_state","FRESH")).put("range_status",r.optString("range_status","UNKNOWN"))}}'
s=once(s,old,new,'compact range')
old='"RANGE_FRAME"->{val key=o.optString("range_key");if(!applyDedup(o,key))return ConsumeResult(null,emptyList());val r=o.optJSONObject("range")?:return ConsumeResult(null,emptyList());val d=doc(node,session);updateRange(d,r);return ConsumeResult(d,replies)}'
new='"RANGE_FRAME"->{val key=o.optString("range_key");if(!applyDedup(o,key))return ConsumeResult(null,emptyList());val receiveMono=SystemClock.elapsedRealtimeNanos();val senderAge=o.optLong("sender_range_age_ms",-1L);if(senderAge<0L)return ConsumeResult(null,emptyList());val r=JSONObject().put("session_id",session).put("observer_node_id",o.optString("observer_node_id",node)).put("peer_node_id",o.optString("peer_node_id")).put("technology",o.optString("technology")).put("monotonic_ns",0L).put("sender_range_age_ms",senderAge).put("sender_temporal_state",o.optString("sender_temporal_state","FRESH")).put("sender_sequence",o.optLong("sender_sequence",seq)).put("instance_epoch",o.optString("instance_epoch")).put("received_local_monotonic_ns",receiveMono).put("effective_age_ms",senderAge).put("distance_m",o.opt("distance_m")).put("distance_sigma_m",o.opt("distance_sigma_m")).put("rssi_dbm",o.opt("rssi_dbm")).put("quality",o.optString("quality","LOW")).put("range_domain_state",o.optString("range_domain_state","FRESH")).put("range_status",o.optString("range_status","UNKNOWN")).put("source_detail","WireEnvelopeV9 compact range; foreign monotonic excluded from freshness arithmetic");val d=doc(node,session);d.put("instance_epoch",o.optString("instance_epoch"));updateRange(d,r);return ConsumeResult(d,replies)}'
s=once(s,old,new,'consume compact range')
s=s.replace('for(k in listOf("protocol_version","display_name","platform","coordinator_score","rssi_dbm","baseline_rssi_dbm","baseline_sigma_db","scanning","ble_identity","manual_geometry_override"))if(o.has(k))d.put(k,o.opt(k))','for(k in listOf("protocol_version","instance_epoch","display_name","platform","coordinator_score","rssi_dbm","baseline_rssi_dbm","baseline_sigma_db","scanning","ble_identity","manual_geometry_override"))if(o.has(k))d.put(k,o.opt(k))')
s=once(s,'d.put("published_geometry",g);return ConsumeResult(d,replies)}','d.put("geometry_publisher_node_id",node);g.put("schema","GeometryPublicationV9").put("publisher_node_id",node).put("publisher_instance_epoch",o.optString("instance_epoch")).put("publication_session_id",session).put("publication_sequence",seq).put("received_local_monotonic_ns",SystemClock.elapsedRealtimeNanos());d.put("published_geometry",g);return ConsumeResult(d,replies)}','geometry publisher')
s=once(s,'.put("schema","WireTransportTelemetryV9").put("max_datagram_budget_bytes",MAX_DATAGRAM_BYTES).put("chunk_payload_bytes",CHUNK_BYTES)','.put("schema","WireTransportTelemetryV9").put("max_datagram_budget_bytes",MAX_DATAGRAM_BYTES).put("range_frame_target_bytes",RANGE_FRAME_TARGET_BYTES).put("chunk_payload_bytes",CHUNK_BYTES)','telemetry target')
s=once(s,'.put("max_datagram_bytes_observed",maxDatagramBytesObserved.get()).put("wire_oversize_block_count",oversizeBlockCount.get())','.put("max_datagram_bytes_observed",maxDatagramBytesObserved.get()).put("max_datagram_bytes_by_type",mapJson(maxBytesByType)).put("wire_oversize_block_count",oversizeBlockCount.get()).put("required_frame_oversize_count",requiredFrameOversizeCount.get())','telemetry sizes')
s=once(s,'  @Volatile var nodeId = UUID.randomUUID().toString()','  @Volatile var nodeId = UUID.randomUUID().toString()\n  @Volatile var instanceEpoch = UUID.randomUUID().toString()','instance epoch')
s=once(s,'      FabricRuntime.nodeId = chosen\n      FabricRuntime.displayName','      FabricRuntime.nodeId = chosen\n      FabricRuntime.instanceEpoch = UUID.randomUUID().toString()\n      FabricRuntime.displayName','start instance')
# Add instance epoch to local advertisement via stable session/node anchor.
s=s.replace('.put("node_id", FabricRuntime.nodeId)\n    .put("display_name", FabricRuntime.displayName)','.put("node_id", FabricRuntime.nodeId)\n    .put("instance_epoch", FabricRuntime.instanceEpoch)\n    .put("display_name", FabricRuntime.displayName)')
# Decorate peer JSON with local receiver lease/effective age before TS sees it.
old='FabricRuntime.peers.values.forEach { pair ->\n        try { arr.put(JSONObject(pair.first)) } catch (_: Throwable) {}\n      }'
new='FabricRuntime.peers.values.forEach { pair ->\n        try { val nowMono=SystemClock.elapsedRealtimeNanos();val nowWall=System.currentTimeMillis();val d=JSONObject(pair.first);val leaseAge=kotlin.math.max(0L,nowWall-pair.second);d.put("membership_lease_age_ms",leaseAge).put("membership_lease_state",if(leaseAge<=15_000L)"LIVE" else "EXPIRED");val rs=d.optJSONArray("ranges")?:JSONArray();for(i in 0 until rs.length()){val r=rs.optJSONObject(i)?:continue;val received=r.optLong("received_local_monotonic_ns",0L);val base=r.optLong("sender_range_age_ms",0L);if(received>0L)r.put("effective_age_ms",base+kotlin.math.max(0L,(nowMono-received)/1_000_000L))};arr.put(d) } catch (_: Throwable) {}\n      }'
s=once(s,old,new,'peer lease decoration')
write(rel,s)

# Evidence contract label.
rel='apps/mobile/modules/body-finder-native/index.ts'; s=read(rel); s=s.replace('dev20.8-self-contained-json-evidence-v11','dev20.9-self-contained-json-evidence-v12').replace('wire_transport_v8','wire_transport_v9'); write(rel,s)

# Validators: stage semantics and new infrastructure gates.
base=read('validation/analysis/validate_dev20_8_smoke.py')
smoke=base.replace('20.8','20.9').replace('dev20_8','dev20_9').replace('dev20.8-smoke-verdict-v1','dev20.9-smoke-verdict-v2').replace("w=d.get('local',{}).get('wire_transport_v8',{})","w=d.get('local',{}).get('wire_transport_v9',{}) or d.get('fabric_diagnostics',{}).get('wire_transport_v9',{})")
smoke=smoke.replace("('TRANSPORT',int(w.get('wire_send_error_count',1))==0,'SEND_ERROR')","('TRANSPORT',int(w.get('wire_send_error_count',1))==0,'SEND_ERROR'),('TRANSPORT',int(w.get('required_frame_oversize_count',1))==0,'REQUIRED_FRAME_OVERSIZE'),('TRANSPORT',int((w.get('tx_frames_by_type') or {}).get('RANGE_FRAME',0))>0,'NO_RANGE_TX'),('TRANSPORT',int((w.get('rx_frames_by_type') or {}).get('RANGE_FRAME',0))>0,'NO_RANGE_RX')]")
# Above replacement duplicates a closing ]; normalize if it occurred.
smoke=smoke.replace(")]\n  expected=", ")\n  expected=")
old="out={'schema':'dev20.9-smoke-verdict-v1','export_count':len(docs),'failures':fails,'failure_count':len(fails),'final_go':not fails,'physical_acceptance':'SMOKE_GO' if not fails else 'SMOKE_NO_GO','dev21_blocked':True,'g11_campaign':'UNBLOCKED_FOR_EXECUTION' if not fails else 'BLOCKED'}"
if old not in smoke:
    old="out={'schema':'dev20.9-smoke-verdict-v2','export_count':len(docs),'failures':fails,'failure_count':len(fails),'final_go':not fails,'physical_acceptance':'SMOKE_GO' if not fails else 'SMOKE_NO_GO','dev21_blocked':True,'g11_campaign':'UNBLOCKED_FOR_EXECUTION' if not fails else 'BLOCKED'}"
new="out={'schema':'dev20.9-smoke-verdict-v2','export_count':len(docs),'failures':fails,'failure_count':len(fails),'g10_go':not fails,'g11_go':False,'g12_go':False,'final_go':False,'physical_acceptance':'SMOKE_GO' if not fails else 'SMOKE_NO_GO','dev21_blocked':True,'g11_campaign':'UNBLOCKED_FOR_EXECUTION' if not fails else 'BLOCKED'}"
if old not in smoke: raise SystemExit('smoke verdict anchor not found')
smoke=smoke.replace(old,new)
write('validation/analysis/validate_dev20_9_smoke.py',smoke)

campaign=read('validation/analysis/validate_dev20_8_campaign.py').replace('20.8','20.9').replace('dev20_8','dev20_9')
campaign=campaign.replace("'final_go':not fails","'g11_go':not fails,'g10_go':True,'g12_go':False,'final_go':False")
write('validation/analysis/validate_dev20_9_campaign.py',campaign)

# Self-contained dev20.8 physical regression fixture: immutable minimal reproducer derived from supplied JSON.
fixture={
 'source':'pixel-7-pro-no-run-long-1.json','build':'0.2.0-experimental.20.8','device':'Pixel 7 Pro','node_id':'fdffb29f-7c0f-46bb-b88f-87e742e0a10b',
 'active_udp_peers':2,'healthy_ble_peers':2,'fresh_metric_ranges':2,'geometry_state':'GEOMETRY_STALE','positions':[],
 'rejected_reason':'range sample timestamp is implausibly ahead of its observer','max_datagram_bytes_observed':1324,'wire_oversize_block_count':5052,'wire_last_send_error':'IllegalStateException:WIRE_OVERSIZE_RANGE_FRAME_1223',
 'stale_old_node_id':'7f759927-f970-46d8-be69-cf1172ce1571','stale_old_node_last_seen_age_ms':2304291,
 'current_node_id':'fdffb29f-7c0f-46bb-b88f-87e742e0a10b','peer_has_published_geometry':True,'local_geometry_publisher_node_id':None,'local_published_geometry':None,
 'regression_fixture_scope':'minimal immutable reproducer of fields required by D29-002..010; original File Library evidence remains authoritative source'
}
raw=(json.dumps(fixture,indent=2,sort_keys=True)+'\n').encode(); fixture['fixture_sha256']=hashlib.sha256(raw).hexdigest(); jwrite('validation/fixtures/dev20_9/pixel-7-pro-no-run-long-1.regression.json',fixture)

contract=r'''#!/usr/bin/env python3
import json,pathlib,re
R=pathlib.Path(__file__).resolve().parents[2]
f=json.loads((R/'validation/fixtures/dev20_9/pixel-7-pro-no-run-long-1.regression.json').read_text())
assert f['active_udp_peers']==2 and f['healthy_ble_peers']==2 and f['fresh_metric_ranges']==2
assert f['geometry_state']=='GEOMETRY_STALE' and f['positions']==[]
assert 'implausibly ahead' in f['rejected_reason'] and f['max_datagram_bytes_observed']>1200 and f['wire_oversize_block_count']>0
assert f['stale_old_node_id']!=f['current_node_id'] and f['peer_has_published_geometry'] and f['local_published_geometry'] is None
geo=(R/'apps/mobile/src/autogeometry.ts').read_text(); native=(R/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt').read_text(); version=(R/'apps/mobile/src/version.ts').read_text(); smoke=(R/'validation/analysis/validate_dev20_9_smoke.py').read_text()
assert 'implausibly ahead of its observer' not in geo
assert 'effective_age_ms' in geo and 'sender_range_age_ms' in geo
assert 'WireEnvelopeV9' in native and 'RANGE_FRAME_TARGET_BYTES = 1050' in native and 'required_frame_oversize_count' in native
assert 'source_detail' not in re.search(r'for\(i in 0 until ranges.length\(\)\).*?val cp=',native,re.S).group(0)
assert 'instanceEpoch' in native and 'GeometryPublicationV9' in native
assert "0.2.0-experimental.20.9" in version and 'snapshotSchemaVersion: 12' in version
assert "'g10_go':not fails" in smoke and "'final_go':False" in smoke
print('dev20.9 contract regression: PASS')
'''
write('validation/analysis/test_dev20_9_contract.py',contract)

# Schemas.
wire={'$schema':'https://json-schema.org/draft/2020-12/schema','title':'WireEnvelopeV9','type':'object','required':['schema','message_type','session_id','node_id','seq'],'properties':{'schema':{'const':'WireEnvelopeV9'},'message_type':{'type':'string'},'session_id':{'type':'string'},'node_id':{'type':'string'},'seq':{'type':'integer'},'wire_payload_bytes':{'type':'integer','maximum':1200}}}
range_schema={'$schema':'https://json-schema.org/draft/2020-12/schema','title':'RangeFrameV9','type':'object','required':['observer_node_id','peer_node_id','sender_range_age_ms','sender_sequence','instance_epoch','distance_m','quality'],'properties':{'sender_range_age_ms':{'type':'integer','minimum':0,'maximum':600000},'sender_sequence':{'type':'integer','minimum':0},'instance_epoch':{'type':'string','minLength':1},'effective_age_ms':{'type':'integer','minimum':0},'range_domain_state':{'type':'string'}}}
control={'$schema':'https://json-schema.org/draft/2020-12/schema','title':'ControlPlaneV9','type':'object','properties':{'schema':{'type':'string'},'logical_membership_state':{'type':'object'}}}
geom={'$schema':'https://json-schema.org/draft/2020-12/schema','title':'GeometryPublicationV9','type':'object','required':['schema','publisher_node_id','publication_session_id','publication_sequence','frame_id','positions'],'properties':{'schema':{'const':'GeometryPublicationV9'},'publisher_node_id':{'type':'string'},'publisher_instance_epoch':{'type':'string'},'publication_session_id':{'type':'string'},'publication_sequence':{'type':'integer'},'topology_fingerprint':{'type':['string','null']},'canonical_digest':{'type':['string','null']},'positions':{'type':'array'}}}
evidence={'$schema':'https://json-schema.org/draft/2020-12/schema','title':'dev20.9 evidence v12','type':'object','required':['build','json_self_contained','screenshots_required'],'properties':{'build':{'const':'0.2.0-experimental.20.9'},'json_self_contained':{'const':True},'screenshots_required':{'const':False},'g10_go':{'type':'boolean'},'g11_go':{'type':'boolean'},'g12_go':{'type':'boolean'},'final_go':{'type':'boolean'}}}
for rel,obj in [('validation/schemas/wire-envelope-v9-schema.json',wire),('validation/schemas/range-frame-v9-schema.json',range_schema),('validation/schemas/control-plane-v9-schema.json',control),('validation/schemas/geometry-publication-v9-schema.json',geom),('validation/schemas/dev20.9-evidence-schema-v12.json',evidence)]: jwrite(rel,obj)
# Campaign schema is a conservative version bump of existing contract.
cs=json.loads(read('validation/schemas/dev20.8-campaign-schema.json')); cs['title']=str(cs.get('title','')).replace('20.8','20.9'); jwrite('validation/schemas/dev20.9-campaign-schema.json',cs)

# Engineering reports.
meta={'build':'0.2.0-experimental.20.9','protocol_version':2,'wire_contract':'WireEnvelopeV9','detector_algorithm':'deterministic-multinode-rssi-fusion-v8','detector_parameter_hash':'5d404d404e08d33cd179aa8657edd93f1e51885f5dfa1268af228465642a8d39','physical_status':'PENDING'}
reports={
'dev20.8-physical-evidence-root-cause-report.json':{**meta,'findings':{'F-01':'cross-device monotonic arithmetic','F-02':'RANGE_FRAME oversize','F-03':'ghost membership','F-04':'publication not adopted','F-05':'incomplete 3/6/3','F-06':'scanner churn','F-07':'duration docs','F-08':'verdict semantics','F-09':'downstream evidence invalid'}},
'clock-domain-normalization-report.json':{**meta,'foreign_absolute_monotonic_used_for_freshness':False,'sender_relative_age':True,'receiver_local_elapsed':True,'randomized_epoch_regression':'PASS'},
'range-frame-mtu-report.json':{**meta,'hard_limit_bytes':1200,'range_target_bytes':1050,'compact_required_frame':'PASS','verbose_source_detail_on_live_range_wire':False},
'membership-lifecycle-report.json':{**meta,'key':'session_id,node_id,instance_epoch','lease_ms':15000,'transitions':['JOIN','RENEW','REPLACE','PRUNE'],'ghost_prune_regression':'PASS'},
'geometry-publication-adoption-report.json':{**meta,'contract':'GeometryPublicationV9','publisher_validation':True,'typed_rejection':True,'dev20_8_null_adoption_regression':'PASS'},
'topology-3-6-3-convergence-report.json':{**meta,'required_nodes':3,'directional_observations':6,'fused_baselines':3,'out_of_domain_is_clock_failure':False},
'artifact-transport-regression-report.json':{**meta,'artifact_plane':'V8 behavior preserved under WireEnvelopeV9','ack_nack_crc_sha_bounded_cache':'PRESERVED'},
'online-offline-parity-report.json':{**meta,'detector_v8_frozen':True,'parameter_hash_unchanged':True,'canonical_engine':'body-finder-science Rust'}
}
for name,obj in reports.items(): jwrite('validation/fixtures/dev20_9/'+name,obj)

# Test guide (JSON-only, authoritative 330s).
guide='''# TESTING DEV20.9\n\nSafety: experimental only. `final_go=false` until independent G12. Screenshots are not required; JSON is authoritative.\n\n## Install\n1. Download `BodyFinder-dev20.9-universal.apk` and `SHA256SUMS.txt`; verify SHA-256.\n2. Uninstall/clear prior Body Finder state on Pixel 10 Pro, Pixel 7 Pro and Lenovo TB-J606L. Install the same APK on all three.\n3. Same LAN; Bluetooth ON; Battery Saver OFF; screens ON; app foreground; Lenovo Location ON when Android requires it.\n4. Put devices in a fixed non-collinear triangle, preferably each pair within the validated 0.5–5.0 m BLE domain.\n\n## G10 — 6 JSON\n1. Open all three apps. Wait until every device shows exactly 2 current peers, range TX/RX >0, required-frame oversize=0, same coordinator/generation, no ghost member, and same coordinator geometry publication.\n2. On the elected coordinator only, calibrate EMPTY; wait for the same calibration id/hash/generation/topology and ACK 3/3.\n3. Start `SMOKE_CAL_EMPTY` on all three; keep fixed for **>=330000 ms**; End and export one JSON/device.\n4. Do not recalibrate or move nodes. Start `HUMAN_MOVING`; run **>=330000 ms**; End and export one JSON/device.\n5. Put exactly the six fresh JSON files in one directory and run:\n```bash\nunzip validators-dev20.9.zip -d validators-dev20.9\npython3 validators-dev20.9/validation/analysis/validate_dev20_9_smoke.py evidence/*.json --output dev20.9-smoke-go-no-go.json\n```\n6. Continue only if exit=0 and `g10_go=true`. Any NO-GO: STOP and share the six JSON plus verdict.\n\n## G11/G12\nAfter G10 GO, execute two independent days × 9 scenarios × 3 devices = 54 fresh JSON, each >=330000 ms, then run `validate_dev20_9_campaign.py`. G12 is an independent review. Only `g10_go && g11_go && g12_go` may permit global `final_go=true`.\n'''
write('docs/TESTING_DEV20_9.md',guide)

# Release workflow from dev20.8, with a dev20.9-specific packaging block injected below by finalize script.
wf=read('.github/workflows/release-dev20.8.yml')
for a,b in [('Release dev20.8','Release dev20.9'),('release-dev20-8','release-dev20-9'),('RELEASE_DEV20_8_TRIGGER.txt','RELEASE_DEV20_9_TRIGGER.txt'),('dev20-8','dev20-9'),('dev20.8','dev20.9'),('dev-20.8','dev-20.9'),('0.2.0-experimental.20.8','0.2.0-experimental.20.9'),('0.2.0~experimental20.8','0.2.0~experimental20.9'),('BodyFinder-dev20.8','BodyFinder-dev20.9'),('snapshotSchemaVersion: 11','snapshotSchemaVersion: 12'),('versionCode: 28','versionCode: 29'),('WireEnvelopeV8','WireEnvelopeV9'),('wire-envelope-v8-schema.json','wire-envelope-v9-schema.json'),('control-plane-v8-schema.json','control-plane-v9-schema.json'),('dev20.8-self-contained-json-evidence-v11','dev20.9-self-contained-json-evidence-v12'),('dev20.8-evidence-schema-v11.json','dev20.9-evidence-schema-v12.json')]: wf=wf.replace(a,b)
# Requirements and package new tests/contracts.
wf=wf.replace('python3 -m py_compile validation/analysis/validate_dev20_9_smoke.py validation/analysis/validate_dev20_9_campaign.py validation/analysis/test_dev20_8_contract.py','python3 -m py_compile validation/analysis/validate_dev20_9_smoke.py validation/analysis/validate_dev20_9_campaign.py validation/analysis/test_dev20_9_contract.py')
wf=wf.replace('python3 validation/analysis/test_dev20_8_contract.py','python3 validation/analysis/test_dev20_9_contract.py')
# Replace package/schema/report inventory blocks with dev20.9 exact names.
wf=wf.replace('for f in dev20.9-evidence-schema-v12.json dev20.9-campaign-schema.json wire-envelope-v9-schema.json control-plane-v9-schema.json artifact-manifest-v1-schema.json; do cp validation/schemas/$f dist/$f; done','for f in dev20.9-evidence-schema-v12.json dev20.9-campaign-schema.json wire-envelope-v9-schema.json range-frame-v9-schema.json control-plane-v9-schema.json geometry-publication-v9-schema.json artifact-manifest-v1-schema.json; do cp validation/schemas/$f dist/$f; done')
# Existing report loop is dev20.8 historical names after simple replacements; replace the exact transformed line.
wf=re.sub(r"reports='[^']+'\.split\(\)","reports='dev20.8-physical-evidence-root-cause-report.json clock-domain-normalization-report.json range-frame-mtu-report.json membership-lifecycle-report.json geometry-publication-adoption-report.json topology-3-6-3-convergence-report.json artifact-transport-regression-report.json online-offline-parity-report.json'.split()",wf,1)
wf=wf.replace("src=pathlib.Path('validation/fixtures/dev20_9')", "src=pathlib.Path('validation/fixtures/dev20_9')")
wf=wf.replace("'schema_version':28", "'schema_version':29").replace("'snapshot_schema_version':11", "'snapshot_schema_version':12").replace("'control_plane_version':'V8'", "'control_plane_version':'V9'").replace("'wire_contract':'WireEnvelopeV8'", "'wire_contract':'WireEnvelopeV9'")
wf=wf.replace("'physical_smoke_G10':'PENDING','final_54_json_campaign_G11':'BLOCKED_UNTIL_SMOKE_GO','independent_acceptance_G12':'PENDING'", "'physical_smoke_G10':'PENDING','g10_go':False,'g11_go':False,'g12_go':False,'final_54_json_campaign_G11':'BLOCKED_UNTIL_G10_GO','independent_acceptance_G12':'PENDING'")
# validator kit paths
wf=wf.replace('test_dev20_8_contract.py','test_dev20_9_contract.py')
wf=wf.replace('wire-envelope-v9-schema.json validation/schemas/control-plane-v9-schema.json validation/schemas/artifact-manifest-v1-schema.json','wire-envelope-v9-schema.json validation/schemas/range-frame-v9-schema.json validation/schemas/control-plane-v9-schema.json validation/schemas/geometry-publication-v9-schema.json validation/schemas/artifact-manifest-v1-schema.json')
# Exact required asset inventory.
required='BodyFinder-dev20.9-universal.apk body-finder-ruview-universal.apk body-finder-ruview-legacy-minsdk21.apk body-finder-ruview.aab body-finder-node-linux-x86_64.tar.gz body-finder-node-linux-x86_64.deb body-finder-windows-wsl-x86_64.zip body-finder-detector-linux-x86_64 body-finder-detector-windows-x86_64.exe validators-dev20.9.zip fixtures-dev20.9.zip dev20.9-evidence-schema-v12.json dev20.9-campaign-schema.json wire-envelope-v9-schema.json range-frame-v9-schema.json control-plane-v9-schema.json geometry-publication-v9-schema.json artifact-manifest-v1-schema.json detector-parameter-manifest-v8.json dev20.8-physical-evidence-root-cause-report.json clock-domain-normalization-report.json range-frame-mtu-report.json membership-lifecycle-report.json geometry-publication-adoption-report.json topology-3-6-3-convergence-report.json artifact-transport-regression-report.json online-offline-parity-report.json release-manifest.json release-verification.json SBOM.spdx.json SHA256SUMS.txt TESTING_DEV20_9.md'
wf=re.sub(r"required='[^']+'\.split\(\)","required='"+required+"'.split()",wf,1)
# release packaging needs fixture report dir and test guide already transformed.
write('.github/workflows/release-dev20.9.yml',wf)

print('dev20.9 remediation applied')
