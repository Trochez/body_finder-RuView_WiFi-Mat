package com.trochez.bodyfindernative

import android.os.Build
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.ConcurrentLinkedDeque
import java.util.concurrent.atomic.AtomicLong
import kotlin.math.max

internal data class ValidationEvent(
  val seq: Long, val wallMs: Long, val type: String, val reason: String,
  val strategy: String, val cohort: String, val rangingState: String, val yieldActive: Boolean,
  val recoveryGeneration: Long?, val peerId: String?, val triggerKind: String?, val triggerPeerId: String?,
  val fromStrategy: String?, val toStrategy: String?, val authorizationReason: String?,
)

internal object ValidationEventLog {
  private const val MAX_RUNTIME = 512
  private const val MAX_RUN = 256
  private val seq = AtomicLong(0)
  private val q = ConcurrentLinkedDeque<ValidationEvent>()
  private var lastWallMs: Long = 0

  @Synchronized fun reset() { seq.set(0); q.clear(); lastWallMs = 0 }
  fun currentSeq(): Long = seq.get()

  @Synchronized fun record(
    type: String, reason: String = "", now: Long = System.currentTimeMillis(),
    peerId: String? = null, triggerKind: String? = null, triggerPeerId: String? = null,
    fromStrategy: String? = null, toStrategy: String? = null, authorizationReason: String? = null,
  ) {
    val eventNow = max(now, lastWallMs); lastWallMs = eventNow
    val generation = BleAcquisitionPolicy.activeRecoveryGeneration()
    val rs = if (Build.VERSION.SDK_INT >= 36) SystemRangingApi36.stateLabel() else "UNSUPPORTED"
    val y = Build.VERSION.SDK_INT >= 36 && SystemRangingApi36.isBleYieldActive(eventNow)
    q.addLast(ValidationEvent(
      seq.incrementAndGet(), eventNow, type, reason,
      BleAcquisitionPolicy.currentStrategy().name, BleAcquisitionPolicy.currentCohortHealth().name,
      rs, y, generation, peerId,
      triggerKind ?: BleAcquisitionPolicy.activeRecoveryTriggerKind()?.name,
      triggerPeerId ?: BleAcquisitionPolicy.activeRecoveryTriggerPeerId(),
      fromStrategy, toStrategy, authorizationReason,
    ))
    while (q.size > MAX_RUNTIME) q.pollFirst()
  }

  @Synchronized fun snapshotSince(after: Long, start: Long): JSONObject {
    val all = q.filter { it.seq > after }; val kept = if (all.size > MAX_RUN) all.takeLast(MAX_RUN) else all
    val a = JSONArray()
    kept.forEach { e -> a.put(JSONObject()
      .put("seq", e.seq).put("wall_ms", e.wallMs)
      .put("elapsed_ms", max(0, e.wallMs - start)).put("elapsed_from_run_start_ms", max(0, e.wallMs - start))
      .put("type", e.type).put("reason", e.reason).put("logical_strategy", e.strategy)
      .put("cohort_health", e.cohort).put("system_ranging_state", e.rangingState).put("ranging_yield_active", e.yieldActive)
      .put("recovery_generation", e.recoveryGeneration ?: JSONObject.NULL).put("peer_id", e.peerId ?: JSONObject.NULL)
      .put("trigger_kind", e.triggerKind ?: JSONObject.NULL).put("trigger_peer_id", e.triggerPeerId ?: JSONObject.NULL)
      .put("from_strategy", e.fromStrategy ?: JSONObject.NULL).put("to_strategy", e.toStrategy ?: JSONObject.NULL)
      .put("authorization_reason", e.authorizationReason ?: JSONObject.NULL)) }
    return JSONObject().put("events", a).put("event_timeline_total_count", all.size).put("event_timeline_truncated", all.size > MAX_RUN)
  }
}
