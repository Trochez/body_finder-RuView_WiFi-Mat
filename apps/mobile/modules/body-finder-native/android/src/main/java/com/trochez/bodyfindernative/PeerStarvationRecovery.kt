package com.trochez.bodyfindernative

import org.json.JSONObject
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicLong
import kotlin.math.max

enum class PeerHealthState { PEER_HEALTHY, PEER_SPARSE, PEER_STARVATION_CANDIDATE, PEER_STARVED, PEER_RECOVERING, PEER_RECOVERY_FAILED }
enum class RecoveryTriggerKind { FULL_COHORT_STALL, PEER_STARVATION }

data class PeerStarvationDecision(val state: PeerHealthState, val becameStarved: Boolean, val requestRecovery: Boolean)

internal data class PeerStarvationRuntime(
  var state: PeerHealthState = PeerHealthState.PEER_HEALTHY,
  var candidateSinceWallMs: Long? = null,
  var starvationSinceWallMs: Long? = null,
  var starvationCount: Long = 0,
  var recoveryParticipationCount: Long = 0,
  var recoverySuccessCount: Long = 0,
  var recoveryFailureCount: Long = 0,
  var lastRecoveryGeneration: Long? = null,
  var lastRecoveryLatencyMs: Long? = null,
)

internal object PeerStarvationRecovery {
  const val CANDIDATE_VALID_SAMPLE_WINDOW_MS=5_000L
  const val PERSISTENCE_MS=6_000L
  private val byPeer=ConcurrentHashMap<String,PeerStarvationRuntime>()
  private val candidateCount=AtomicLong(0)
  private val starvationCount=AtomicLong(0)
  private val requestCount=AtomicLong(0)
  private val successCount=AtomicLong(0)
  private val failureCount=AtomicLong(0)
  @Volatile var lastStarvationWallMs:Long?=null
  @Volatile var lastStarvationPeerId:String?=null

  fun reset(){ byPeer.clear(); candidateCount.set(0); starvationCount.set(0); requestCount.set(0); successCount.set(0); failureCount.set(0); lastStarvationWallMs=null; lastStarvationPeerId=null }
  fun runtime(peerId:String)=byPeer.computeIfAbsent(peerId){PeerStarvationRuntime()}
  fun counters()=longArrayOf(candidateCount.get(),starvationCount.get(),requestCount.get(),successCount.get(),failureCount.get())
  fun peerCounters(peerId:String):LongArray { val x=runtime(peerId); return longArrayOf(x.starvationCount,x.recoveryParticipationCount,x.recoverySuccessCount,x.recoveryFailureCount) }

  @Synchronized fun observe(peerId:String, now:Long, fabricActive:Boolean, bleBound:Boolean, globalHealthy:Boolean, validSamples5s:Int, lastValidAgeMs:Long?, recoveryAlreadyActive:Boolean):PeerStarvationDecision{
    val r=runtime(peerId)
    if(!fabricActive || !bleBound || !globalHealthy){ r.state=PeerHealthState.PEER_HEALTHY; r.candidateSinceWallMs=null; r.starvationSinceWallMs=null; return PeerStarvationDecision(r.state,false,false) }
    if(recoveryAlreadyActive && BleAcquisitionPolicy.lastRecoveryTriggerPeerId()==peerId){ r.state=PeerHealthState.PEER_RECOVERING; return PeerStarvationDecision(r.state,false,false) }
    val candidate=validSamples5s<3 || (lastValidAgeMs!=null && lastValidAgeMs>5_000L)
    if(!candidate){ r.state=PeerHealthState.PEER_HEALTHY; r.candidateSinceWallMs=null; r.starvationSinceWallMs=null; return PeerStarvationDecision(r.state,false,false) }
    if(r.candidateSinceWallMs==null){ r.candidateSinceWallMs=now; r.state=PeerHealthState.PEER_STARVATION_CANDIDATE; candidateCount.incrementAndGet(); ValidationEventLog.record("BF_PEER_STARVATION_CANDIDATE","EXPECTED_ACTIVE_PEER_SPARSE",now=now,peerId=peerId,triggerKind="PEER_STARVATION"); return PeerStarvationDecision(r.state,false,false) }
    if(now-r.candidateSinceWallMs!! < PERSISTENCE_MS){ r.state=PeerHealthState.PEER_SPARSE; return PeerStarvationDecision(r.state,false,false) }
    val became=r.state!=PeerHealthState.PEER_STARVED
    r.state=PeerHealthState.PEER_STARVED
    if(became){ r.starvationSinceWallMs=now; r.starvationCount++; starvationCount.incrementAndGet(); lastStarvationWallMs=now; lastStarvationPeerId=peerId; ValidationEventLog.record("BF_PEER_STARVED","EXPECTED_ACTIVE_PEER_PERSISTENT_SAMPLE_STARVATION",now=now,peerId=peerId,triggerKind="PEER_STARVATION") }
    return PeerStarvationDecision(r.state,became,!recoveryAlreadyActive)
  }

  fun noteRecoveryRequested(peerId:String,generation:Long){ val r=runtime(peerId); r.state=PeerHealthState.PEER_RECOVERING; r.recoveryParticipationCount++; r.lastRecoveryGeneration=generation; requestCount.incrementAndGet() }
  fun noteRecoverySuccess(peerId:String,latency:Long?){ val r=runtime(peerId); r.state=PeerHealthState.PEER_HEALTHY; r.candidateSinceWallMs=null; r.starvationSinceWallMs=null; r.recoverySuccessCount++; r.lastRecoveryLatencyMs=latency; successCount.incrementAndGet() }
  fun noteRecoveryFailure(peerId:String,latency:Long?){ val r=runtime(peerId); r.state=PeerHealthState.PEER_RECOVERY_FAILED; r.recoveryFailureCount++; r.lastRecoveryLatencyMs=latency; failureCount.incrementAndGet() }
  fun diagnostics(peerId:String):JSONObject{ val r=runtime(peerId); return JSONObject().put("peer_health_state",r.state.name).put("starvation_candidate_since_wall_ms",r.candidateSinceWallMs?:JSONObject.NULL).put("starvation_since_wall_ms",r.starvationSinceWallMs?:JSONObject.NULL).put("starvation_count",r.starvationCount).put("starvation_recovery_participation_count",r.recoveryParticipationCount).put("starvation_recovery_success_count",r.recoverySuccessCount).put("starvation_recovery_failure_count",r.recoveryFailureCount).put("last_starvation_recovery_generation",r.lastRecoveryGeneration?:JSONObject.NULL).put("last_starvation_recovery_latency_ms",r.lastRecoveryLatencyMs?:JSONObject.NULL) }
}
