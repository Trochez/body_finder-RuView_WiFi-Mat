#!/usr/bin/env python3
from __future__ import annotations
import pathlib

ROOT=pathlib.Path(__file__).resolve().parents[1]

def patch(path,old,new):
 p=ROOT/path;s=p.read_text(encoding='utf-8');c=s.count(old)
 if c!=1: raise SystemExit(f'{path}: expected 1 occurrence, got {c}: {old[:100]!r}')
 p.write_text(s.replace(old,new,1),encoding='utf-8')

# Authority diagnostics: bounded convergence timeline and rejection count are exported as part
# of authority_status, which is embedded in PRE_RUN and acceptance JSON evidence.
a='apps/mobile/src/authority.ts'
patch(a,
 "const states=new Map<string,State>();",
 "const states=new Map<string,State>();\ntype AuthorityConvergenceEvent={wall_ms:number;generation:number;ack_count:number;consensus:boolean;base_digest:string;authority_view_digest:string};\nconst convergenceBySession=new Map<string,AuthorityConvergenceEvent[]>();\nfunction noteConvergence(sid:string,view:AuthorityViewV1,ackCount:number,consensus:boolean){const prior=convergenceBySession.get(sid)??[],last=prior.at(-1);if(!last||last.generation!==view.coordinator_generation||last.ack_count!==ackCount||last.authority_view_digest!==view.authority_view_digest||last.consensus!==consensus){prior.push({wall_ms:Date.now(),generation:view.coordinator_generation,ack_count:ackCount,consensus,base_digest:view.base_digest,authority_view_digest:view.authority_view_digest});convergenceBySession.set(sid,prior.slice(-64))}}")
patch(a,
 "const ack_count=ack_matrix.filter(x=>x.acknowledged).length,consensus=ids.length===3&&ack_count===3;return{schema:'AuthorityStatusV2',view,canonical_cohort_input:view.cohort,base_digest:view.base_digest,authority_view_digest:view.authority_view_digest,coordinator_generation:view.coordinator_generation,ack_matrix,ack_count,consensus,blocking_reasons:consensus?[]:['AUTHORITY_ACK_3_OF_3_REQUIRED']}}",
 "const ack_count=ack_matrix.filter(x=>x.acknowledged).length,consensus=ids.length===3&&ack_count===3,rejected_ack_count=ids.filter(id=>id!==localNodeId).filter(id=>{const cp=(nodes.find(n=>n.node_id===id)?.control_plane as any);return Boolean(cp?.authority_ack_v1)&&!ack_matrix.find(x=>x.node_id===id)?.acknowledged}).length;noteConvergence(sid,view,ack_count,consensus);const convergence_timeline=convergenceBySession.get(sid)??[];return{schema:'AuthorityStatusV2',view,canonical_cohort_input:view.cohort,base_digest:view.base_digest,authority_view_digest:view.authority_view_digest,coordinator_generation:view.coordinator_generation,authority_generation_history:convergence_timeline.map(x=>({wall_ms:x.wall_ms,generation:x.generation,base_digest:x.base_digest,authority_view_digest:x.authority_view_digest})),convergence_timeline,stale_or_foreign_ack_rejection_count:rejected_ack_count,ack_matrix,ack_count,consensus,blocking_reasons:consensus?[]:['AUTHORITY_ACK_3_OF_3_REQUIRED']}}")

k='apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt'
patch(k,
 "  private val maxControlBytesByKey=java.util.concurrent.ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong>()\n  private val oversizeControlKeyCounts",
 "  private val maxControlBytesByKey=java.util.concurrent.ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong>()\n  private val maxControlPayloadBytesByKey=java.util.concurrent.ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong>()\n  private val oversizeControlKeyCounts")
patch(k,
 "  val sendErrorCount=java.util.concurrent.atomic.AtomicLong(0)\n  val maxDatagramBytesObserved",
 "  val sendErrorCount=java.util.concurrent.atomic.AtomicLong(0)\n  val networkRecoveryAttemptCount=java.util.concurrent.atomic.AtomicLong(0)\n  val networkRecoverySuccessCount=java.util.concurrent.atomic.AtomicLong(0)\n  val networkRecoveryFailureCount=java.util.concurrent.atomic.AtomicLong(0)\n  @Volatile var lastNetworkRecoveryError:String?=null\n  val maxDatagramBytesObserved")
patch(k,
 "    val compact=JSONObject().put(\"control_key\",key).put(\"control_value\",value).toString().toByteArray(Charsets.UTF_8)\n    if(compact.size>COMPACT_CONTROL_PAYLOAD_TARGET_BYTES)",
 "    val compact=JSONObject().put(\"control_key\",key).put(\"control_value\",value).toString().toByteArray(Charsets.UTF_8)\n    maxControlPayloadBytesByKey.computeIfAbsent(key){AtomicLong(0)}.updateAndGet{v->kotlin.math.max(v,compact.size.toLong())}\n    if(compact.size>COMPACT_CONTROL_PAYLOAD_TARGET_BYTES)")
patch(k,
 "    .put(\"max_datagram_bytes_observed\",maxDatagramBytesObserved.get()).put(\"max_datagram_bytes_by_type\",mapJson(maxBytesByType)).put(\"oversize_drop_by_type\",mapJson(oversizeDropByType)).put(\"wire_oversize_block_count\",oversizeBlockCount.get()).put(\"required_frame_oversize_count\",requiredFrameOversizeCount.get()).put(\"max_control_bytes_by_key\",mapJson(maxControlBytesByKey)).put(\"oversize_control_key_counts\",mapJson(oversizeControlKeyCounts))",
 "    .put(\"max_datagram_bytes_observed\",maxDatagramBytesObserved.get()).put(\"max_datagram_bytes_by_type\",mapJson(maxBytesByType)).put(\"oversize_drop_by_type\",mapJson(oversizeDropByType)).put(\"wire_oversize_block_count\",oversizeBlockCount.get()).put(\"required_frame_oversize_count\",requiredFrameOversizeCount.get()).put(\"max_control_bytes_by_key\",mapJson(maxControlBytesByKey)).put(\"max_control_payload_bytes_by_key\",mapJson(maxControlPayloadBytesByKey)).put(\"oversize_control_key_counts\",mapJson(oversizeControlKeyCounts))")
patch(k,
 "    .put(\"wire_send_error_count\",sendErrorCount.get()).put(\"wire_last_send_error\",lastSendError?:JSONObject.NULL).put(\"wire_receive_error_count\",receiveErrorCount.get())",
 "    .put(\"wire_send_error_count\",sendErrorCount.get()).put(\"wire_last_send_error\",lastSendError?:JSONObject.NULL).put(\"network_recovery_attempt_count\",networkRecoveryAttemptCount.get()).put(\"network_recovery_success_count\",networkRecoverySuccessCount.get()).put(\"network_recovery_failure_count\",networkRecoveryFailureCount.get()).put(\"last_network_recovery_error\",lastNetworkRecoveryError?:JSONObject.NULL).put(\"wire_receive_error_count\",receiveErrorCount.get())")
patch(k,
 "          if (now >= nextSend) {\n            val ad = advertisement(ctx)",
 "          val networkError=WireTransportV10.lastSendError.orEmpty();if(networkError.contains(\"ENETUNREACH\",ignoreCase=true)||networkError.contains(\"Network is unreachable\",ignoreCase=true)){WireTransportV10.networkRecoveryAttemptCount.incrementAndGet();try{try{socket.leaveGroup(groupAddress)}catch(_:Throwable){};socket.joinGroup(groupAddress);FabricRuntime.multicastJoinState=\"REJOINED_AFTER_ENETUNREACH\";WireTransportV10.networkRecoverySuccessCount.incrementAndGet();WireTransportV10.lastNetworkRecoveryError=null;WireTransportV10.lastSendError=null}catch(t:Throwable){WireTransportV10.networkRecoveryFailureCount.incrementAndGet();WireTransportV10.lastNetworkRecoveryError=\"${t.javaClass.simpleName}:${t.message}\"}}\n          if (now >= nextSend) {\n            val ad = advertisement(ctx)")

print('dev20.14 post patch applied')
