from pathlib import Path
import json, shutil, textwrap, re

ROOT = Path(__file__).resolve().parents[1]

def read(rel): return (ROOT/rel).read_text()
def write(rel, text):
    p=ROOT/rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text)

def replace_once(rel, old, new):
    p=ROOT/rel; s=p.read_text()
    n=s.count(old)
    if n != 1:
        raise SystemExit(f'{rel}: expected exactly one anchor, found {n}: {old[:120]!r}')
    p.write_text(s.replace(old,new,1))

def replace_all(rel, old, new, min_count=1):
    p=ROOT/rel; s=p.read_text(); n=s.count(old)
    if n < min_count: raise SystemExit(f'{rel}: expected >= {min_count} {old!r}, found {n}')
    p.write_text(s.replace(old,new))

# ---------------------------------------------------------------------------
# Version truth
# ---------------------------------------------------------------------------
replace_all('apps/mobile/src/version.ts', '0.2.0-experimental.11', '0.2.0-experimental.12')
replace_once('apps/mobile/src/version.ts', 'reportVersion: 13', 'reportVersion: 14')
replace_once('apps/mobile/src/version.ts', 'versionCode: 11', 'versionCode: 12')
replace_all('apps/mobile/src/version.ts', "releaseIteration: 'experimental.11'", "releaseIteration: 'experimental.12'")
replace_once('apps/mobile/app.json', '"versionCode": 11', '"versionCode": 12')
replace_once('apps/mobile/app.json', '"releaseIteration": "experimental.11"', '"releaseIteration": "experimental.12"')
replace_all('apps/mobile/App.tsx', 'experimental.11', 'experimental.12', min_count=3)

# ---------------------------------------------------------------------------
# Recovery policy: one arbiter, per-peer trigger provenance, terminal exactly-once
# ---------------------------------------------------------------------------
POL='apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleAcquisitionPolicy.kt'
replace_once(POL,
'''enum class BodyFinderCohortHealth {
  BF_COHORT_HEALTHY,
  BF_COHORT_SPARSE,
  BF_COHORT_STALLED,
  BF_COHORT_RECOVERING,
  BF_COHORT_UNAVAILABLE,
}
''',
'''enum class BodyFinderCohortHealth {
  BF_COHORT_HEALTHY,
  BF_COHORT_SPARSE,
  BF_COHORT_STALLED,
  BF_COHORT_RECOVERING,
  BF_COHORT_UNAVAILABLE,
}

enum class RecoveryTriggerKind {
  FULL_COHORT_STALL,
  PEER_STARVATION,
}

enum class PeerHealthState {
  PEER_HEALTHY,
  PEER_SPARSE,
  PEER_STARVATION_CANDIDATE,
  PEER_STARVED,
  PEER_RECOVERING,
  PEER_RECOVERY_FAILED,
}
''')
replace_once(POL,
'''  const val COHORT_STALL_THRESHOLD_MS = 5_000L
  const val RECOVERY_UNFILTERED_WINDOW_MS = 10_000L
''',
'''  const val COHORT_STALL_THRESHOLD_MS = 5_000L
  const val PEER_STARVATION_PERSIST_MS = 6_000L
  const val RECOVERY_UNFILTERED_WINDOW_MS = 10_000L
''')
replace_once(POL,
'''  private val recoveryGenerationCounter = AtomicLong(0)
  @Volatile private var activeRecoveryGeneration: Long? = null
  private val recoverySuccessGeneration = AtomicLong(0)
  private val recoveryFailureGeneration = AtomicLong(0)
''',
'''  private val recoveryGenerationCounter = AtomicLong(0)
  @Volatile private var activeRecoveryGeneration: Long? = null
  @Volatile private var activeRecoveryTriggerKind: RecoveryTriggerKind? = null
  @Volatile private var activeRecoveryTriggerPeerId: String? = null
  @Volatile private var lastRecoveryTriggerKind: RecoveryTriggerKind? = null
  @Volatile private var lastRecoveryTriggerPeerId: String? = null
  @Volatile private var lastPeerStarvationWallMs: Long? = null
  @Volatile private var lastPeerStarvationPeerId: String? = null
  @Volatile private var peerStarvationCount: Long = 0L
  @Volatile private var peerStarvationRecoveryRequestCount: Long = 0L
  @Volatile private var peerStarvationRecoverySuccessCount: Long = 0L
  @Volatile private var peerStarvationRecoveryFailureCount: Long = 0L
  private val recoverySuccessGeneration = AtomicLong(0)
  private val recoveryFailureGeneration = AtomicLong(0)
  private val recoveryTerminalGeneration = AtomicLong(0)
''')
replace_once(POL,
'''    activeRecoveryGeneration = null
    recoverySuccessGeneration.set(0)
    recoveryFailureGeneration.set(0)
''',
'''    activeRecoveryGeneration = null
    activeRecoveryTriggerKind = null
    activeRecoveryTriggerPeerId = null
    lastRecoveryTriggerKind = null
    lastRecoveryTriggerPeerId = null
    lastPeerStarvationWallMs = null
    lastPeerStarvationPeerId = null
    peerStarvationCount = 0
    peerStarvationRecoveryRequestCount = 0
    peerStarvationRecoverySuccessCount = 0
    peerStarvationRecoveryFailureCount = 0
    recoverySuccessGeneration.set(0)
    recoveryFailureGeneration.set(0)
    recoveryTerminalGeneration.set(0)
''')
replace_once(POL,
'''  fun activeRecoveryGeneration(): Long? = activeRecoveryGeneration
  fun currentRecoveryGeneration(): Long = activeRecoveryGeneration ?: recoveryGenerationCounter.get()
''',
'''  fun activeRecoveryGeneration(): Long? = activeRecoveryGeneration
  fun activeRecoveryTriggerKind(): RecoveryTriggerKind? = activeRecoveryTriggerKind
  fun activeRecoveryTriggerPeerId(): String? = activeRecoveryTriggerPeerId
  fun currentRecoveryGeneration(): Long = activeRecoveryGeneration ?: recoveryGenerationCounter.get()
  fun peerStarvationCount(): Long = peerStarvationCount
  fun peerStarvationRecoveryRequestCount(): Long = peerStarvationRecoveryRequestCount
  fun peerStarvationRecoverySuccessCount(): Long = peerStarvationRecoverySuccessCount
  fun peerStarvationRecoveryFailureCount(): Long = peerStarvationRecoveryFailureCount

  @Synchronized
  fun notePeerStarved(now: Long, peerId: String) {
    peerStarvationCount++
    lastPeerStarvationWallMs = now
    lastPeerStarvationPeerId = peerId
  }

  fun recoveryCallbackEligible(peerId: String?): Boolean =
    activeRecoveryTriggerKind != RecoveryTriggerKind.PEER_STARVATION ||
      (peerId != null && peerId == activeRecoveryTriggerPeerId)
''')
replace_once(POL,
'''    if (next == BleAcquisitionStrategy.FILTERED_PRIMARY || next == BleAcquisitionStrategy.FAILED_SAFE) {
      activeRecoveryGeneration = null
    }
''',
'''    if (next == BleAcquisitionStrategy.FILTERED_PRIMARY || next == BleAcquisitionStrategy.FAILED_SAFE) {
      activeRecoveryGeneration = null
      activeRecoveryTriggerKind = null
      activeRecoveryTriggerPeerId = null
    }
''')
replace_once(POL,
'''  fun beginRecovery(now: Long, reason: String) {
    recoveryAttemptCountTotal++
    recoveryAttemptWallMs.addLast(now)
    val generation = recoveryGenerationCounter.incrementAndGet()
    activeRecoveryGeneration = generation
    recoveryStartedWallMs = now
    lastRecoveryAttemptWallMs = now
    cohortHealth = BodyFinderCohortHealth.BF_COHORT_RECOVERING
    ValidationEventLog.record("RECOVERY_REQUESTED", reason, now = now)
    transition(BleAcquisitionStrategy.UNFILTERED_RECOVERY, now, reason)
  }

  @Synchronized
  fun noteRecoverySuccess(now: Long) {
    val generation = activeRecoveryGeneration ?: return
    if (recoverySuccessGeneration.get() == generation) return
    recoverySuccessGeneration.set(generation)
    val start = recoveryStartedWallMs
    if (start != null) lastRecoveryLatencyMs = max(0L, now - start)
    cohortRecoveryCount++
    ValidationEventLog.record("RECOVERY_SUCCESS", "FIRST_VALID_BF_CALLBACK", now = now)
    recoveryStartedWallMs = null
  }

  @Synchronized
  fun noteRecoveryFailure(now: Long = System.currentTimeMillis()) {
    val generation = activeRecoveryGeneration ?: return
    if (recoveryFailureGeneration.get() == generation) return
    recoveryFailureGeneration.set(generation)
    cohortRecoveryFailureCount++
    ValidationEventLog.record("RECOVERY_FAILURE", "RECOVERY_WINDOW_EXPIRED", now = now)
    recoveryStartedWallMs = null
  }
''',
'''  fun beginRecovery(
    now: Long,
    reason: String,
    triggerKind: RecoveryTriggerKind = RecoveryTriggerKind.FULL_COHORT_STALL,
    triggerPeerId: String? = null,
  ) {
    if (activeRecoveryGeneration != null) return
    recoveryAttemptCountTotal++
    recoveryAttemptWallMs.addLast(now)
    val generation = recoveryGenerationCounter.incrementAndGet()
    activeRecoveryGeneration = generation
    activeRecoveryTriggerKind = triggerKind
    activeRecoveryTriggerPeerId = triggerPeerId
    lastRecoveryTriggerKind = triggerKind
    lastRecoveryTriggerPeerId = triggerPeerId
    if (triggerKind == RecoveryTriggerKind.PEER_STARVATION) peerStarvationRecoveryRequestCount++
    recoveryStartedWallMs = now
    lastRecoveryAttemptWallMs = now
    cohortHealth = BodyFinderCohortHealth.BF_COHORT_RECOVERING
    ValidationEventLog.record(
      "RECOVERY_REQUESTED", reason, now = now,
      peerId = triggerPeerId, triggerKind = triggerKind.name,
    )
    transition(BleAcquisitionStrategy.UNFILTERED_RECOVERY, now, reason)
  }

  @Synchronized
  fun noteRecoverySuccess(now: Long, peerId: String? = null) {
    val generation = activeRecoveryGeneration ?: return
    if (!recoveryCallbackEligible(peerId)) return
    if (recoveryTerminalGeneration.get() == generation) return
    recoveryTerminalGeneration.set(generation)
    recoverySuccessGeneration.set(generation)
    val start = recoveryStartedWallMs
    if (start != null) lastRecoveryLatencyMs = max(0L, now - start)
    cohortRecoveryCount++
    if (activeRecoveryTriggerKind == RecoveryTriggerKind.PEER_STARVATION) peerStarvationRecoverySuccessCount++
    ValidationEventLog.record(
      "RECOVERY_SUCCESS", "FIRST_VALID_BF_CALLBACK", now = now,
      peerId = activeRecoveryTriggerPeerId ?: peerId,
      triggerKind = activeRecoveryTriggerKind?.name,
    )
    recoveryStartedWallMs = null
  }

  @Synchronized
  fun noteRecoveryFailure(now: Long = System.currentTimeMillis()) {
    val generation = activeRecoveryGeneration ?: return
    if (recoveryTerminalGeneration.get() == generation) return
    recoveryTerminalGeneration.set(generation)
    recoveryFailureGeneration.set(generation)
    cohortRecoveryFailureCount++
    if (activeRecoveryTriggerKind == RecoveryTriggerKind.PEER_STARVATION) peerStarvationRecoveryFailureCount++
    ValidationEventLog.record(
      "RECOVERY_FAILURE", "RECOVERY_WINDOW_EXPIRED", now = now,
      peerId = activeRecoveryTriggerPeerId,
      triggerKind = activeRecoveryTriggerKind?.name,
    )
    recoveryStartedWallMs = null
  }
''')
replace_once(POL,
'''    .put("cohort_stall_threshold_ms", COHORT_STALL_THRESHOLD_MS)
    .put("global_scanner_fresh_ms", GLOBAL_SCANNER_FRESH_MS)
''',
'''    .put("cohort_stall_threshold_ms", COHORT_STALL_THRESHOLD_MS)
    .put("peer_starvation_persist_ms", PEER_STARVATION_PERSIST_MS)
    .put("global_scanner_fresh_ms", GLOBAL_SCANNER_FRESH_MS)
    .put("peer_starvation_candidate_count", 0)
    .put("peer_starvation_count", peerStarvationCount)
    .put("peer_starvation_recovery_request_count", peerStarvationRecoveryRequestCount)
    .put("peer_starvation_recovery_success_count", peerStarvationRecoverySuccessCount)
    .put("peer_starvation_recovery_failure_count", peerStarvationRecoveryFailureCount)
    .put("last_peer_starvation_wall_ms", lastPeerStarvationWallMs ?: JSONObject.NULL)
    .put("last_peer_starvation_peer_id", lastPeerStarvationPeerId ?: JSONObject.NULL)
    .put("last_recovery_trigger_kind", lastRecoveryTriggerKind?.name ?: JSONObject.NULL)
    .put("last_recovery_trigger_peer_id", lastRecoveryTriggerPeerId ?: JSONObject.NULL)
    .put("active_recovery_trigger_kind", activeRecoveryTriggerKind?.name ?: JSONObject.NULL)
    .put("active_recovery_trigger_peer_id", activeRecoveryTriggerPeerId ?: JSONObject.NULL)
''')
# Targeted recovery participation counters must not credit the wrong peer.
replace_once(POL,
'''      if (strategy == BleAcquisitionStrategy.UNFILTERED_RECOVERY) {
        val generation = BleAcquisitionPolicy.activeRecoveryGeneration()
        if (generation != null) {
          if (markGeneration(lastRecoveryGenerationSeen, generation)) recoveryParticipationCount.incrementAndGet()
          if (markGeneration(lastFirstValidRecoveryGeneration, generation)) firstCallbackAfterRecoveryCount.incrementAndGet()
          val started = BleAcquisitionPolicy.recoveryStartedMs()
          if (started != null) lastRecoveryCallbackLatencyMs.set(max(0L, now - started))
        }
      }
''',
'''      if (strategy == BleAcquisitionStrategy.UNFILTERED_RECOVERY) {
        val generation = BleAcquisitionPolicy.activeRecoveryGeneration()
        if (generation != null) {
          if (markGeneration(lastRecoveryGenerationSeen, generation)) recoveryParticipationCount.incrementAndGet()
          val started = BleAcquisitionPolicy.recoveryStartedMs()
          if (started != null) lastRecoveryCallbackLatencyMs.set(max(0L, now - started))
        }
      }
''')

# ---------------------------------------------------------------------------
# Timeline: explicit peer + trigger provenance, target-gated first valid event
# ---------------------------------------------------------------------------
EV='apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/ValidationEventLog.kt'
replace_once(EV,
'''  val yieldActive: Boolean,
  val recoveryGeneration: Long?,
)''',
'''  val yieldActive: Boolean,
  val recoveryGeneration: Long?,
  val peerId: String?,
  val triggerKind: String?,
)''')
replace_once(EV,
'''  fun record(type: String, reason: String = "", now: Long = System.currentTimeMillis()) {
    val generation = BleAcquisitionPolicy.activeRecoveryGeneration()
    if (type == "FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY") {
      val g = generation ?: return
      if (firstCallbackRecordedGeneration == g) return
      firstCallbackRecordedGeneration = g
    }
''',
'''  fun record(
    type: String,
    reason: String = "",
    now: Long = System.currentTimeMillis(),
    peerId: String? = null,
    triggerKind: String? = null,
  ) {
    val generation = BleAcquisitionPolicy.activeRecoveryGeneration()
    if (type == "FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY") {
      val g = generation ?: return
      if (!BleAcquisitionPolicy.recoveryCallbackEligible(peerId)) return
      if (firstCallbackRecordedGeneration == g) return
      firstCallbackRecordedGeneration = g
    }
''')
replace_once(EV,
'''        rs, y, generation,
      )''',
'''        rs, y, generation, peerId,
        triggerKind ?: BleAcquisitionPolicy.activeRecoveryTriggerKind()?.name,
      )''')
replace_once(EV,
'''          .put("recovery_generation", e.recoveryGeneration ?: JSONObject.NULL)
''',
'''          .put("recovery_generation", e.recoveryGeneration ?: JSONObject.NULL)
          .put("peer_id", e.peerId ?: JSONObject.NULL)
          .put("trigger_kind", e.triggerKind ?: JSONObject.NULL)
          .put("trigger_peer_id", if (e.triggerKind == RecoveryTriggerKind.PEER_STARVATION.name) (e.peerId ?: JSONObject.NULL) else JSONObject.NULL)
''')

# ---------------------------------------------------------------------------
# Native runtime: per-peer starvation state, targeted success, keep-awake,
# acceptance duration, complete JSON preflight/diagnostics.
# ---------------------------------------------------------------------------
MOD='apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt'
replace_once(MOD, 'import android.os.SystemClock\n', 'import android.os.SystemClock\nimport android.view.WindowManager\n')
replace_once(MOD,
'''private data class CompletedValidationRun(val runId: String, val snapshotJson: String)
''',
'''private data class CompletedValidationRun(val runId: String, val snapshotJson: String)
private data class PeerStarvationCounterSnapshot(
  val starvationCount: Long,
  val recoveryParticipationCount: Long,
  val recoverySuccessCount: Long,
  val recoveryFailureCount: Long,
)
''')
replace_once(MOD,
'''  @Volatile private var baselineEventSeq: Long = 0
  @Volatile private var validationTruthJson: String = "{}"
''',
'''  @Volatile private var baselineEventSeq: Long = 0
  @Volatile private var baselinePeerStarvation: Long = 0
  @Volatile private var baselinePeerStarvationRecoveryRequest: Long = 0
  @Volatile private var baselinePeerStarvationRecoverySuccess: Long = 0
  @Volatile private var baselinePeerStarvationRecoveryFailure: Long = 0
  @Volatile private var validationTruthJson: String = "{}"
''')
replace_once(MOD,
'''    baselineEventSeq = ValidationEventLog.currentSeq()
    validationTruthJson = "{}"
''',
'''    baselineEventSeq = ValidationEventLog.currentSeq()
    baselinePeerStarvation = BleAcquisitionPolicy.peerStarvationCount()
    baselinePeerStarvationRecoveryRequest = BleAcquisitionPolicy.peerStarvationRecoveryRequestCount()
    baselinePeerStarvationRecoverySuccess = BleAcquisitionPolicy.peerStarvationRecoverySuccessCount()
    baselinePeerStarvationRecoveryFailure = BleAcquisitionPolicy.peerStarvationRecoveryFailureCount()
    validationTruthJson = "{}"
''')
replace_once(MOD,
'''      .put("recovery_attempt_delta", base.optLong("recovery_attempt_delta"))
      .put("cohort_stall_delta", base.optLong("cohort_stall_delta"))
''',
'''      .put("recovery_attempt_delta", base.optLong("recovery_attempt_delta"))
      .put("cohort_stall_delta", base.optLong("cohort_stall_delta"))
      .put("peer_starvation_delta", base.optLong("peer_starvation_delta"))
      .put("peer_starvation_recovery_request_delta", base.optLong("peer_starvation_recovery_request_delta"))
      .put("peer_starvation_recovery_success_delta", base.optLong("peer_starvation_recovery_success_delta"))
      .put("peer_starvation_recovery_failure_delta", base.optLong("peer_starvation_recovery_failure_delta"))
''')
replace_once(MOD,
'''      .put("elapsed_ms", elapsed)
      .put("app_visibility", appVisibility)
''',
'''      .put("elapsed_ms", elapsed)
      .put("acceptance_minimum_ms", 300_000L)
      .put("acceptance_duration_eligible", elapsed >= 300_000L)
      .put("short_diagnostic_run", elapsed in 1 until 300_000L)
      .put("keep_awake_policy", "FLAG_KEEP_SCREEN_ON_DURING_ACTIVE_VALIDATION")
      .put("app_visibility", appVisibility)
''')
replace_once(MOD,
'''      .put("recovery_attempt_delta", (BleAcquisitionPolicy.recoveryAttemptCount() - baselineRecoveryAttempts).coerceAtLeast(0))
      .put("restart_suppressed_delta", (BleAcquisitionPolicy.restartSuppressedCount() - baselineRestartSuppressed).coerceAtLeast(0))
''',
'''      .put("recovery_attempt_delta", (BleAcquisitionPolicy.recoveryAttemptCount() - baselineRecoveryAttempts).coerceAtLeast(0))
      .put("restart_suppressed_delta", (BleAcquisitionPolicy.restartSuppressedCount() - baselineRestartSuppressed).coerceAtLeast(0))
      .put("peer_starvation_delta", (BleAcquisitionPolicy.peerStarvationCount() - baselinePeerStarvation).coerceAtLeast(0))
      .put("peer_starvation_recovery_request_delta", (BleAcquisitionPolicy.peerStarvationRecoveryRequestCount() - baselinePeerStarvationRecoveryRequest).coerceAtLeast(0))
      .put("peer_starvation_recovery_success_delta", (BleAcquisitionPolicy.peerStarvationRecoverySuccessCount() - baselinePeerStarvationRecoverySuccess).coerceAtLeast(0))
      .put("peer_starvation_recovery_failure_delta", (BleAcquisitionPolicy.peerStarvationRecoveryFailureCount() - baselinePeerStarvationRecoveryFailure).coerceAtLeast(0))
''')
replace_once(MOD,
'''  val validationAcquisitionBaselineByIdentity = ConcurrentHashMap<String, BleAcquisitionCounterSnapshot>()
  val addressRebindCountByIdentity = ConcurrentHashMap<String, AtomicLong>()
''',
'''  val validationAcquisitionBaselineByIdentity = ConcurrentHashMap<String, BleAcquisitionCounterSnapshot>()
  val peerHealthStateByPeer = ConcurrentHashMap<String, String>()
  val starvationCandidateSinceByPeer = ConcurrentHashMap<String, Long>()
  val starvationSinceByPeer = ConcurrentHashMap<String, Long>()
  val peerStarvationCountByPeer = ConcurrentHashMap<String, AtomicLong>()
  val peerStarvationRecoveryParticipationByPeer = ConcurrentHashMap<String, AtomicLong>()
  val peerStarvationRecoverySuccessByPeer = ConcurrentHashMap<String, AtomicLong>()
  val peerStarvationRecoveryFailureByPeer = ConcurrentHashMap<String, AtomicLong>()
  val peerLastStarvationRecoveryGeneration = ConcurrentHashMap<String, Long>()
  val peerLastStarvationRecoveryLatencyMs = ConcurrentHashMap<String, Long>()
  val validationStarvationBaselineByPeer = ConcurrentHashMap<String, PeerStarvationCounterSnapshot>()
  val addressRebindCountByIdentity = ConcurrentHashMap<String, AtomicLong>()
''')
replace_once(MOD,
'''    validationAcquisitionBaselineByIdentity.clear()
    invalidRssiEventsByIdentity.clear()
''',
'''    validationAcquisitionBaselineByIdentity.clear()
    peerHealthStateByPeer.clear()
    starvationCandidateSinceByPeer.clear()
    starvationSinceByPeer.clear()
    peerStarvationCountByPeer.clear()
    peerStarvationRecoveryParticipationByPeer.clear()
    peerStarvationRecoverySuccessByPeer.clear()
    peerStarvationRecoveryFailureByPeer.clear()
    peerLastStarvationRecoveryGeneration.clear()
    peerLastStarvationRecoveryLatencyMs.clear()
    validationStarvationBaselineByPeer.clear()
    invalidRssiEventsByIdentity.clear()
''')
replace_once(MOD,
'''  fun snapshotAcquisitionForValidation() {
    validationAcquisitionBaselineByIdentity.clear()
    acquisitionStatsByIdentity.forEach { (identity, stats) ->
      validationAcquisitionBaselineByIdentity[identity] = stats.snapshot()
    }
  }
''',
'''  fun snapshotAcquisitionForValidation() {
    validationAcquisitionBaselineByIdentity.clear()
    acquisitionStatsByIdentity.forEach { (identity, stats) ->
      validationAcquisitionBaselineByIdentity[identity] = stats.snapshot()
    }
    validationStarvationBaselineByPeer.clear()
    peers.keys.forEach { peerId ->
      validationStarvationBaselineByPeer[peerId] = PeerStarvationCounterSnapshot(
        peerStarvationCountByPeer[peerId]?.get() ?: 0,
        peerStarvationRecoveryParticipationByPeer[peerId]?.get() ?: 0,
        peerStarvationRecoverySuccessByPeer[peerId]?.get() ?: 0,
        peerStarvationRecoveryFailureByPeer[peerId]?.get() ?: 0,
      )
    }
  }
''')
# Start/end keep-awake and duration warning remains non-blocking.
replace_once(MOD,
'''      ValidationRuntime.start(
        now,
        FabricRuntime.peerExpireCount.get(),
        FabricRuntime.totalRebinds(),
        FabricRuntime.scanRestartCount.get(),
        FabricRuntime.txPackets.get(),
        FabricRuntime.rxPackets.get(),
      )
''',
'''      val id = ValidationRuntime.start(
        now,
        FabricRuntime.peerExpireCount.get(),
        FabricRuntime.totalRebinds(),
        FabricRuntime.scanRestartCount.get(),
        FabricRuntime.txPackets.get(),
        FabricRuntime.rxPackets.get(),
      )
      setValidationKeepAwake(true)
      id
''')
replace_once(MOD,
'''      ValidationRuntime.end(now,FabricRuntime.peerExpireCount.get(),FabricRuntime.totalRebinds(),FabricRuntime.scanRestartCount.get(),FabricRuntime.txPackets.get(),FabricRuntime.rxPackets.get(),acquisitionProvenance(now),peerBleDiagnostics(now),if(Build.VERSION.SDK_INT>=36) SystemRangingApi36.diagnostics(now) else JSONObject().put("state","UNSUPPORTED"))
      true
''',
'''      ValidationRuntime.end(now,FabricRuntime.peerExpireCount.get(),FabricRuntime.totalRebinds(),FabricRuntime.scanRestartCount.get(),FabricRuntime.txPackets.get(),FabricRuntime.rxPackets.get(),acquisitionProvenance(now),peerBleDiagnostics(now),if(Build.VERSION.SDK_INT>=36) SystemRangingApi36.diagnostics(now) else JSONObject().put("state","UNSUPPORTED"))
      setValidationKeepAwake(false)
      true
''')
replace_once(MOD,
'''    Function("stopFabric") {
      val ctx = appContext.reactContext
      if (ctx != null) stopFieldService(ctx.applicationContext)
      FabricRuntime.stop()
      true
    }
''',
'''    Function("stopFabric") {
      val ctx = appContext.reactContext
      setValidationKeepAwake(false)
      if (ctx != null) stopFieldService(ctx.applicationContext)
      FabricRuntime.stop()
      true
    }
''')
replace_once(MOD,
'''  private fun probe(state: String, detail: String) = JSONObject().put("state", state).put("detail", detail)
''',
'''  private fun setValidationKeepAwake(enabled: Boolean) {
    val activity = appContext.currentActivity ?: return
    activity.runOnUiThread {
      if (enabled) activity.window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
      else activity.window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    }
  }

  private fun probe(state: String, detail: String) = JSONObject().put("state", state).put("detail", detail)
''')
# Expanded preflight contract.
replace_once(MOD,
'''    if (FieldServiceState.state != "RUNNING") issues += "FIELD_SERVICE_NOT_RUNNING"
    val manager = ctx.getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager
    if (manager?.adapter?.isEnabled != true) issues += "BLUETOOTH_OFF"
    return issues
  }
''',
'''    if (FieldServiceState.state != "RUNNING") issues += "FIELD_SERVICE_NOT_RUNNING"
    val manager = ctx.getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager
    if (manager?.adapter?.isEnabled != true) issues += "BLUETOOTH_OFF"
    if (Build.VERSION.SDK_INT < 31 && locationServiceEnabled(ctx) == false) issues += "LOCATION_OFF"
    if (expectedKnownPeerCount() < 2) issues += "EXPECTED_BLE_PEERS_LT_2"
    if (BleAcquisitionPolicy.currentStrategy() != BleAcquisitionStrategy.FILTERED_PRIMARY) issues += "NOT_FILTERED_PRIMARY"
    if (!FabricRuntime.bleScanning) issues += "BLE_SCANNER_NOT_RUNNING"
    return issues.distinct()
  }

  private fun validationPreflight(ctx: Context, now: Long = System.currentTimeMillis()): JSONObject {
    val issues = validationEnvironmentIssues(ctx)
    val hardwareFilterCount = if (BleAcquisitionPolicy.currentStrategy() == BleAcquisitionStrategy.UNFILTERED_RECOVERY) 0 else 1
    return JSONObject()
      .put("captured_wall_ms", now)
      .put("ready", issues.isEmpty())
      .put("issues", JSONArray(issues))
      .put("bluetooth_on", (ctx.getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager)?.adapter?.isEnabled == true)
      .put("battery_saver_off", (ctx.getSystemService(Context.POWER_SERVICE) as? PowerManager)?.isPowerSaveMode != true)
      .put("screen_on", (ctx.getSystemService(Context.POWER_SERVICE) as? PowerManager)?.isInteractive == true)
      .put("app_foreground", ValidationRuntime.appVisibility == "active")
      .put("foreground_service_running", FieldServiceState.state == "RUNNING")
      .put("expected_ble_peers", expectedKnownPeerCount())
      .put("expected_ble_peers_ready", expectedKnownPeerCount() >= 2)
      .put("acquisition_strategy", BleAcquisitionPolicy.currentStrategy().name)
      .put("filter_mode", if (hardwareFilterCount > 0) "MANUFACTURER_FILTERED" else "UNFILTERED")
      .put("hardware_filter_count", hardwareFilterCount)
      .put("location_service_enabled", locationServiceEnabled(ctx) ?: JSONObject.NULL)
      .put("acceptance_minimum_ms", 300_000L)
      .put("recommended_long_run_ms", 330_000L)
  }
''')
# Helpers + starvation evaluator before scanner maintenance.
replace_once(MOD,
'''  private fun restartScannerWithStrategy(now: Long, strategy: BleAcquisitionStrategy, reason: String): Boolean {
''',
'''  private fun peerIdentity(peerId: String): String? = FabricRuntime.peers[peerId]?.first?.let { raw ->
    try { JSONObject(raw).optString("ble_identity").takeIf { it.isNotBlank() && it != "null" } } catch (_: Throwable) { null }
  }

  private fun peerIdForIdentity(identity: String): String? = FabricRuntime.peers.entries.firstNotNullOfOrNull { (peerId, pair) ->
    try {
      val id = JSONObject(pair.first).optString("ble_identity")
      peerId.takeIf { id == identity }
    } catch (_: Throwable) { null }
  }

  private fun evaluatePeerStarvation(now: Long, global: GlobalBleScannerHealth, cohort: BodyFinderCohortHealth): String? {
    if (global != GlobalBleScannerHealth.GLOBAL_SCANNER_HEALTHY || cohort == BodyFinderCohortHealth.BF_COHORT_STALLED) return null
    val activePeers = FabricRuntime.peers.keys.sorted()
    var selected: String? = null
    for (peerId in activePeers) {
      val identity = peerIdentity(peerId) ?: continue
      val previouslyBound = (FabricRuntime.bleSeenCountByIdentity[identity]?.get() ?: 0L) > 0L || FabricRuntime.lastValidRangeByPeer.containsKey(peerId)
      if (!previouslyBound) continue
      val valid5s = validSamples(identity, now, RANGE_FRESHNESS_MS).size
      val lastValid = FabricRuntime.lastValidRssiWallMsByIdentity[identity]
      val candidate = valid5s < MIN_SAMPLES_FOR_RANGE || (lastValid != null && now - lastValid > RANGE_FRESHNESS_MS)
      if (!candidate) {
        FabricRuntime.starvationCandidateSinceByPeer.remove(peerId)
        FabricRuntime.starvationSinceByPeer.remove(peerId)
        FabricRuntime.peerHealthStateByPeer[peerId] = PeerHealthState.PEER_HEALTHY.name
        continue
      }
      val since = FabricRuntime.starvationCandidateSinceByPeer.putIfAbsent(peerId, now) ?: now
      val age = max(0L, now - since)
      if (age < BleAcquisitionPolicy.PEER_STARVATION_PERSIST_MS) {
        if (FabricRuntime.peerHealthStateByPeer[peerId] != PeerHealthState.PEER_STARVATION_CANDIDATE.name) {
          FabricRuntime.peerHealthStateByPeer[peerId] = PeerHealthState.PEER_STARVATION_CANDIDATE.name
          ValidationEventLog.record(
            "BF_PEER_STARVATION_CANDIDATE",
            "EXPECTED_ACTIVE_PEER_SPARSE_SAMPLES",
            now = now, peerId = peerId, triggerKind = RecoveryTriggerKind.PEER_STARVATION.name,
          )
        }
        continue
      }
      if (FabricRuntime.peerHealthStateByPeer[peerId] != PeerHealthState.PEER_STARVED.name &&
          FabricRuntime.peerHealthStateByPeer[peerId] != PeerHealthState.PEER_RECOVERING.name) {
        FabricRuntime.peerHealthStateByPeer[peerId] = PeerHealthState.PEER_STARVED.name
        FabricRuntime.starvationSinceByPeer[peerId] = now
        FabricRuntime.peerStarvationCountByPeer.computeIfAbsent(peerId) { AtomicLong(0) }.incrementAndGet()
        BleAcquisitionPolicy.notePeerStarved(now, peerId)
        ValidationEventLog.record(
          "BF_PEER_STARVED",
          "EXPECTED_ACTIVE_PEER_PERSISTENT_SAMPLE_STARVATION",
          now = now, peerId = peerId, triggerKind = RecoveryTriggerKind.PEER_STARVATION.name,
        )
      }
      if (selected == null) selected = peerId
    }
    return selected
  }

  private fun restartScannerWithStrategy(now: Long, strategy: BleAcquisitionStrategy, reason: String): Boolean {
''')
# Replace adaptive scanner with target-aware branch. Preserve full-cohort priority.
replace_once(MOD,
'''      BleAcquisitionStrategy.FILTERED_PRIMARY -> {
        if (cohort == BodyFinderCohortHealth.BF_COHORT_STALLED) {
          if (BleAcquisitionPolicy.canStartRecovery(now)) {
            BleAcquisitionPolicy.beginRecovery(now, "BF_COHORT_STALLED")
            restartScannerWithStrategy(now, BleAcquisitionStrategy.UNFILTERED_RECOVERY, "BF_COHORT_STALLED")
          } else if(BleAcquisitionPolicy.recoveryAttemptsInWindow(now)>=BleAcquisitionPolicy.MAX_RECOVERY_ATTEMPTS_PER_5MIN) BleAcquisitionPolicy.markFailedSafe(now,"MAX_RECOVERY_ATTEMPTS")
        }
      }
      BleAcquisitionStrategy.UNFILTERED_RECOVERY -> {
        val started = BleAcquisitionPolicy.recoveryStartedMs() ?: now
        val recovered = recentKnownPeerCount(now) > 0 && FabricRuntime.lastBodyFinderScanResultWallMs?.let { it >= started } == true
        if (recovered) {
          BleAcquisitionPolicy.noteRecoverySuccess(now)
          restartScannerWithStrategy(now, BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE, "BF_COHORT_RECOVERED")
        } else if (now - started >= BleAcquisitionPolicy.RECOVERY_UNFILTERED_WINDOW_MS) {
          BleAcquisitionPolicy.noteRecoveryFailure(now)
          restartScannerWithStrategy(now, BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE, "RECOVERY_WINDOW_EXPIRED")
        }
      }
''',
'''      BleAcquisitionStrategy.FILTERED_PRIMARY -> {
        if (cohort == BodyFinderCohortHealth.BF_COHORT_STALLED) {
          if (BleAcquisitionPolicy.canStartRecovery(now)) {
            BleAcquisitionPolicy.beginRecovery(now, "BF_COHORT_STALLED", RecoveryTriggerKind.FULL_COHORT_STALL)
            restartScannerWithStrategy(now, BleAcquisitionStrategy.UNFILTERED_RECOVERY, "BF_COHORT_STALLED")
          } else if(BleAcquisitionPolicy.recoveryAttemptsInWindow(now)>=BleAcquisitionPolicy.MAX_RECOVERY_ATTEMPTS_PER_5MIN) BleAcquisitionPolicy.markFailedSafe(now,"MAX_RECOVERY_ATTEMPTS")
        } else {
          val environmentAllowsRecovery = ValidationRuntime.runId == null || ValidationRuntime.endedWallMs != null || validationEnvironmentIssues(ctx).isEmpty()
          val starvedPeer = if (environmentAllowsRecovery) evaluatePeerStarvation(now, global, cohort) else null
          if (starvedPeer != null && BleAcquisitionPolicy.canStartRecovery(now)) {
            BleAcquisitionPolicy.beginRecovery(now, "PEER_STARVATION", RecoveryTriggerKind.PEER_STARVATION, starvedPeer)
            FabricRuntime.peerHealthStateByPeer[starvedPeer] = PeerHealthState.PEER_RECOVERING.name
            FabricRuntime.peerStarvationRecoveryParticipationByPeer.computeIfAbsent(starvedPeer) { AtomicLong(0) }.incrementAndGet()
            FabricRuntime.peerLastStarvationRecoveryGeneration[starvedPeer] = BleAcquisitionPolicy.currentRecoveryGeneration()
            restartScannerWithStrategy(now, BleAcquisitionStrategy.UNFILTERED_RECOVERY, "PEER_STARVATION")
          }
        }
      }
      BleAcquisitionStrategy.UNFILTERED_RECOVERY -> {
        val started = BleAcquisitionPolicy.recoveryStartedMs() ?: now
        val triggerPeer = BleAcquisitionPolicy.activeRecoveryTriggerPeerId()
        val recoveredPeerId = if (BleAcquisitionPolicy.activeRecoveryTriggerKind() == RecoveryTriggerKind.PEER_STARVATION) {
          triggerPeer?.takeIf { peerId ->
            val identity = peerIdentity(peerId) ?: return@takeIf false
            FabricRuntime.lastValidRssiWallMsByIdentity[identity]?.let { it >= started } == true
          }
        } else {
          FabricRuntime.peers.keys.firstOrNull { peerId ->
            val identity = peerIdentity(peerId) ?: return@firstOrNull false
            FabricRuntime.lastValidRssiWallMsByIdentity[identity]?.let { it >= started } == true
          }
        }
        if (recoveredPeerId != null) {
          BleAcquisitionPolicy.noteRecoverySuccess(now, recoveredPeerId)
          if (triggerPeer != null && BleAcquisitionPolicy.activeRecoveryTriggerKind() == RecoveryTriggerKind.PEER_STARVATION) {
            FabricRuntime.peerHealthStateByPeer[triggerPeer] = PeerHealthState.PEER_HEALTHY.name
            FabricRuntime.starvationCandidateSinceByPeer.remove(triggerPeer)
            FabricRuntime.starvationSinceByPeer.remove(triggerPeer)
            FabricRuntime.peerStarvationRecoverySuccessByPeer.computeIfAbsent(triggerPeer) { AtomicLong(0) }.incrementAndGet()
            FabricRuntime.peerLastStarvationRecoveryLatencyMs[triggerPeer] = max(0L, now - started)
          }
          restartScannerWithStrategy(now, BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE, "BF_COHORT_RECOVERED")
        } else if (now - started >= BleAcquisitionPolicy.RECOVERY_UNFILTERED_WINDOW_MS) {
          BleAcquisitionPolicy.noteRecoveryFailure(now)
          if (triggerPeer != null && BleAcquisitionPolicy.activeRecoveryTriggerKind() == RecoveryTriggerKind.PEER_STARVATION) {
            FabricRuntime.peerHealthStateByPeer[triggerPeer] = PeerHealthState.PEER_RECOVERY_FAILED.name
            FabricRuntime.peerStarvationRecoveryFailureByPeer.computeIfAbsent(triggerPeer) { AtomicLong(0) }.incrementAndGet()
          }
          restartScannerWithStrategy(now, BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE, "RECOVERY_WINDOW_EXPIRED")
        }
      }
''')
# Probe retries keep full-cohort trigger semantics.
replace_all(MOD, 'BleAcquisitionPolicy.beginRecovery(now, "PROBE_STALLED")', 'BleAcquisitionPolicy.beginRecovery(now, "PROBE_STALLED", RecoveryTriggerKind.FULL_COHORT_STALL)', min_count=1)
# Target gate the exactly-once timeline event.
replace_once(MOD,
'''    if (validRssi && BleAcquisitionPolicy.currentStrategy() == BleAcquisitionStrategy.UNFILTERED_RECOVERY) ValidationEventLog.record("FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY", "BODY_FINDER_CALLBACK", now = now)
''',
'''    val callbackPeerId = peerIdForIdentity(id)
    if (validRssi && BleAcquisitionPolicy.currentStrategy() == BleAcquisitionStrategy.UNFILTERED_RECOVERY && BleAcquisitionPolicy.recoveryCallbackEligible(callbackPeerId)) {
      ValidationEventLog.record(
        "FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY", "BODY_FINDER_CALLBACK", now = now,
        peerId = callbackPeerId, triggerKind = BleAcquisitionPolicy.activeRecoveryTriggerKind()?.name,
      )
    }
''')
# Per-peer exported starvation truth and run-scoped counters.
replace_once(MOD,
'''        val acquisitionStats = identity?.let { FabricRuntime.acquisitionStatsByIdentity[it] }
        val acquisitionBaseline = identity?.let { FabricRuntime.validationAcquisitionBaselineByIdentity[it] }
''',
'''        val acquisitionStats = identity?.let { FabricRuntime.acquisitionStatsByIdentity[it] }
        val acquisitionBaseline = identity?.let { FabricRuntime.validationAcquisitionBaselineByIdentity[it] }
        val starvationBaseline = FabricRuntime.validationStarvationBaselineByPeer[peerId]
        fun starvationDelta(current: Long, baseline: Long?): Long = (current - (baseline ?: 0L)).coerceAtLeast(0L)
''')
replace_once(MOD,
'''          put("peer_gap_state", peerGapState)
''',
'''          put("peer_gap_state", peerGapState)
          put("peer_health_state", FabricRuntime.peerHealthStateByPeer[peerId] ?: if (peerGapState == "PEER_SAMPLE_HEALTHY") PeerHealthState.PEER_HEALTHY.name else PeerHealthState.PEER_SPARSE.name)
          put("starvation_candidate_since_wall_ms", FabricRuntime.starvationCandidateSinceByPeer[peerId] ?: JSONObject.NULL)
          put("starvation_since_wall_ms", FabricRuntime.starvationSinceByPeer[peerId] ?: JSONObject.NULL)
          put("starvation_count", FabricRuntime.peerStarvationCountByPeer[peerId]?.get() ?: 0)
          put("starvation_recovery_participation_count", FabricRuntime.peerStarvationRecoveryParticipationByPeer[peerId]?.get() ?: 0)
          put("last_starvation_recovery_generation", FabricRuntime.peerLastStarvationRecoveryGeneration[peerId] ?: JSONObject.NULL)
          put("last_starvation_recovery_latency_ms", FabricRuntime.peerLastStarvationRecoveryLatencyMs[peerId] ?: JSONObject.NULL)
          put("run_starvation_count", starvationDelta(FabricRuntime.peerStarvationCountByPeer[peerId]?.get() ?: 0, starvationBaseline?.starvationCount))
          put("run_starvation_recovery_participation_count", starvationDelta(FabricRuntime.peerStarvationRecoveryParticipationByPeer[peerId]?.get() ?: 0, starvationBaseline?.recoveryParticipationCount))
          put("run_starvation_recovery_success_count", starvationDelta(FabricRuntime.peerStarvationRecoverySuccessByPeer[peerId]?.get() ?: 0, starvationBaseline?.recoverySuccessCount))
          put("run_starvation_recovery_failure_count", starvationDelta(FabricRuntime.peerStarvationRecoveryFailureByPeer[peerId]?.get() ?: 0, starvationBaseline?.recoveryFailureCount))
''')
# Diagnostics export includes preflight and an explicit evidence contract.
replace_once(MOD,
'''    return JSONObject()
      .put("ble_diagnostics", bleDiagnostics(ctx, now))
''',
'''    return JSONObject()
      .put("diagnostic_contract", JSONObject()
        .put("schema", "dev12-self-contained-json-evidence-v1")
        .put("screenshots_required", false)
        .put("json_self_contained", true)
        .put("contains_runtime_preflight", true)
        .put("contains_system_ranging", true)
        .put("contains_recovery_causality", true)
        .put("contains_frozen_geometry", true))
      .put("validation_preflight", validationPreflight(ctx, now))
      .put("ble_diagnostics", bleDiagnostics(ctx, now))
''')

# ---------------------------------------------------------------------------
# Mobile JSON export + UX: no screenshots, self-diagnostic gate summary.
# ---------------------------------------------------------------------------
APP='apps/mobile/App.tsx'
replace_once(APP,
'''      truth: 'LIVE_DEVICE_CAPABILITIES__VALIDATED_COARSE_BLE_METRIC_0P5_TO_5M__BOUNDED_HOLDOVER__ADAPTIVE_FILTERED_PRIMARY_WITH_BF_COHORT_RECOVERY__RANGING_MANAGER_BLE_YIELD__RECIPROCAL_FUSION__AUTOGEOMETRY_EXPERIMENTAL_NOT_RESCUE_VALIDATED',
      manual_geometry_override: false, human_scanning_enabled: HUMAN_SCANNING_ENABLED,
''',
'''      truth: 'LIVE_DEVICE_CAPABILITIES__VALIDATED_COARSE_BLE_METRIC_0P5_TO_5M__BOUNDED_HOLDOVER__ADAPTIVE_FILTERED_PRIMARY_WITH_FULL_COHORT_AND_PER_PEER_STARVATION_RECOVERY__RANGING_MANAGER_BLE_YIELD__RECIPROCAL_FUSION__AUTOGEOMETRY_EXPERIMENTAL_NOT_RESCUE_VALIDATED',
      evidence_contract: {
        schema: 'dev12-self-contained-json-evidence-v1', screenshots_required: false, json_self_contained: true,
        required_external_input: 'ground_truth_distances_only_for_accuracy_report',
        diagnostic_source: 'this JSON export',
      },
      manual_geometry_override: false, human_scanning_enabled: HUMAN_SCANNING_ENABLED,
''')
replace_once(APP,
'''      lifecycle_diagnostics: freshDiagnostics?.lifecycle_diagnostics ?? null,
      selected_validation_run_id: freshDiagnostics?.selected_validation_run_id ?? null,
''',
'''      lifecycle_diagnostics: freshDiagnostics?.lifecycle_diagnostics ?? null,
      validation_preflight: freshDiagnostics?.validation_preflight ?? null,
      diagnostic_contract: freshDiagnostics?.diagnostic_contract ?? null,
      selected_validation_run_id: freshDiagnostics?.selected_validation_run_id ?? null,
''')
replace_once(APP,
'''      instructions: 'Return both exports and screenshots from the 5-minute experimental.12 validation-integrity run plus the 3-minute post-End immutability interval. Do not change calibration, minSamples, freshness, holdover or solver settings. Human scanning remains blocked until acquisition continuity is accepted.',
    };
    await Share.share({ message: JSON.stringify(payload, null, 2), title: 'Body Finder experimental.12 validation integrity result' });
''',
'''      self_diagnostic: {
        acceptance_duration_eligible: Boolean(freshDiagnostics?.validation_run?.acceptance_duration_eligible),
        environment_valid: Boolean(freshDiagnostics?.validation_run?.environment_valid),
        snapshot_frozen: Boolean(freshDiagnostics?.validation_run?.snapshot_frozen),
        usable_metric_gate_pass: typeof freshDiagnostics?.validation_run?.usable_metric_range_uptime_percent === 'number' && freshDiagnostics.validation_run.usable_metric_range_uptime_percent >= 90,
        geometry_2d_gate_pass: typeof freshDiagnostics?.validation_run?.geometry_2d_uptime_percent === 'number' && freshDiagnostics.validation_run.geometry_2d_uptime_percent >= 90,
        peer_expire_gate_pass: freshDiagnostics?.validation_run?.peer_expire_delta === 0,
        recovery_budget_gate_pass: typeof freshDiagnostics?.validation_run?.recovery_attempt_delta === 'number' && freshDiagnostics.validation_run.recovery_attempt_delta <= 3,
      },
      instructions: 'Return the exported JSON files only. Screenshots are not required for dev-12 evidence. Use >=330 s for acceptance; short runs remain diagnostic only. Do not change calibration, minSamples, freshness, holdover or solver settings. Human scanning remains blocked.',
    };
    await Share.share({ message: JSON.stringify(payload, null, 2), title: 'Body Finder experimental.12 self-contained validation result' });
''')
replace_once(APP,
'''            <Text style={s.text}>elapsed: {validationRun?.elapsed_ms ?? 0} ms · frozen: {String(Boolean(validationRun?.snapshot_frozen))} · schema: {validationRun?.snapshot_schema_version ?? RELEASE.snapshotSchemaVersion}</Text>
''',
'''            <Text style={s.text}>elapsed: {validationRun?.elapsed_ms ?? 0} ms · acceptance ≥300s: {String(Boolean(validationRun?.acceptance_duration_eligible))} · frozen: {String(Boolean(validationRun?.snapshot_frozen))} · schema: {validationRun?.snapshot_schema_version ?? RELEASE.snapshotSchemaVersion}</Text>
''')
replace_once(APP,
'''            ['Validation run', diagnostics?.validation_run ?? null], ['Lifecycle / power diagnostics', diagnostics?.lifecycle_diagnostics ?? null],
''',
'''            ['Validation preflight', diagnostics?.validation_preflight ?? null], ['Validation run', diagnostics?.validation_run ?? null], ['Lifecycle / power diagnostics', diagnostics?.lifecycle_diagnostics ?? null],
''')

# ---------------------------------------------------------------------------
# dev12 documentation / deterministic validators / fixtures
# ---------------------------------------------------------------------------
write('DEV12_FROZEN_TRUTH.md', '''# dev-12 frozen truth\n\nThe BLE physics remain unchanged from dev-11: profile android-ble-lab-v1; RSSI@1m -69.19 dBm; n=3.62; valid domain 0.5-5.0 m; minSamples=3; fresh=5000 ms; holdover/hard expiry=10000 ms; sigma aging=0.15 m/s; FILTERED_PRIMARY; UNFILTERED_RECOVERY; cooldown=30000 ms; max recovery attempts=3/5 min; API36 BLE yield=120000 ms; protocol=2. Human scanning/localization/rescue remain disabled.\n\ndev-12 adds per-peer persistent starvation recovery and self-contained JSON evidence. Screenshots are not acceptance evidence.\n''')
write('docs/TESTING_DEV12.md', '''# TESTING_DEV12\n\n## 1. Install\nInstall `body-finder-ruview-universal.apk` on the three Android devices. Verify all three APK files have the same SHA-256 from `SHA256SUMS`. Keep the same session (`body-finder-lab`).\n\n## 2. Arrange the devices\nUse Pixel 10 Pro, Pixel 7 Pro and Lenovo TB-J606L, stationary, in a 0.5-5.0 m triangle. Measure the three pairwise distances with a tape and save them separately for the optional accuracy report. Do **not** enter ground truth into the app.\n\n## 3. Preflight on each Android\nOpen Expert and verify `Validation preflight.ready=true`: Bluetooth ON, Battery Saver OFF, screen ON, app foreground, foreground service RUNNING, two expected BLE peers, `FILTERED_PRIMARY`, `MANUFACTURER_FILTERED`, `hardware_filter_count>0`; on Android <=11 Location must be ON.\n\n## 4. Acceptance run\nWarm up >=30 s. Start Validation on all three devices. The app requests keep-awake while the run is active. Leave devices stationary for >=330 s. End each run. `acceptance_duration_eligible` must be true.\n\n## 5. Export evidence — JSON only\nExport the selected long run as `*_run_long_export1.json`. Leave the app running >=180 s, export the **same** run as `*_run_long_export2.json`. Create a short diagnostic run (<300 s), end it (expected `acceptance_duration_eligible=false`), reselect the long run, export `*_run_long_after_short_run.json`. **Screenshots are not required.** Each JSON contains preflight, environment, BLE per-peer state, starvation/recovery causality, system-ranging state, frozen geometry/fusion/graph data and a self-diagnostic gate summary.\n\n## 6. Validate on Ubuntu / WSL / Windows\nUnzip `validators-dev12.zip`, then run:\n\n```bash\npython3 build_acceptance_report.py --device pixel10=pixel10_run_long_export1.json --device pixel7=pixel7_run_long_export1.json --device lenovo=lenovo_run_long_export1.json --out acceptance_report.json\npython3 validate_snapshot_immutability.py pixel10_run_long_export1.json pixel10_run_long_export2.json pixel10_run_long_after_short_run.json\npython3 validate_snapshot_immutability.py pixel7_run_long_export1.json pixel7_run_long_export2.json pixel7_run_long_after_short_run.json\npython3 validate_snapshot_immutability.py lenovo_run_long_export1.json lenovo_run_long_export2.json lenovo_run_long_after_short_run.json\n```\n\nHard acceptance per device: frozen snapshot; elapsed >=300000 ms; duration eligible; environment valid; usable metric >=90%; Geometry2D >=90%; peer_expire_delta=0; recovery attempts <=3. Accuracy remains `COARSE` and informative.\n''')

validators = {
'validate_dev12_hard_gates.py': r'''#!/usr/bin/env python3
import json,sys
p=sys.argv[1]; d=json.load(open(p)); r=d.get('validation_run',d)
checks={
'snapshot_frozen': r.get('snapshot_frozen') is True,
'elapsed_ms>=300000': r.get('elapsed_ms',0)>=300000,
'acceptance_duration_eligible': r.get('acceptance_duration_eligible') is True,
'usable_metric>=90': (r.get('usable_metric_range_uptime_percent') or 0)>=90,
'geometry_2d>=90': (r.get('geometry_2d_uptime_percent') or 0)>=90,
'peer_expire_delta=0': r.get('peer_expire_delta')==0,
'recovery_attempt_delta<=3': r.get('recovery_attempt_delta',99)<=3,
'environment_valid': r.get('environment_valid') is True,
}
print(json.dumps({'file':p,'checks':checks,'pass':all(checks.values())},indent=2)); sys.exit(0 if all(checks.values()) else 1)
''',
'validate_snapshot_immutability.py': r'''#!/usr/bin/env python3
import json,sys
files=sys.argv[1:]; runs=[json.load(open(p)).get('validation_run',json.load(open(p))) for p in files]
canon=[json.dumps(r,sort_keys=True,separators=(',',':')) for r in runs]
ok=len(set(canon))==1
print(json.dumps({'files':files,'validation_run_identical':ok},indent=2)); sys.exit(0 if ok else 1)
''',
'validate_timeline_causality.py': r'''#!/usr/bin/env python3
import json,sys
r=json.load(open(sys.argv[1])).get('validation_run',{})
ev=r.get('events',[]); ok=True; errs=[]
for key in ('seq','wall_ms','elapsed_from_run_start_ms'):
 vals=[e.get(key,0) for e in ev]
 if vals!=sorted(vals): ok=False; errs.append('non_monotonic_'+key)
by={}
for e in ev:
 g=e.get('recovery_generation')
 if g is None: continue
 by.setdefault(g,[]).append(e)
for g,es in by.items():
 req=[e for e in es if e.get('type')=='RECOVERY_REQUESTED']; first=[e for e in es if e.get('type')=='FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY']; term=[e for e in es if e.get('type') in ('RECOVERY_SUCCESS','RECOVERY_FAILURE')]
 if len(req)>1 or len(first)>1 or len(term)>1: ok=False; errs.append(f'exactly_once_generation_{g}')
 if req and term and req[0].get('seq',0)>term[0].get('seq',0): ok=False; errs.append(f'causal_inversion_{g}')
 if req and req[0].get('trigger_kind')=='PEER_STARVATION' and first and first[0].get('peer_id')!=req[0].get('trigger_peer_id'): ok=False; errs.append(f'wrong_target_first_valid_{g}')
print(json.dumps({'pass':ok,'errors':errs,'generation_count':len(by)},indent=2)); sys.exit(0 if ok else 1)
''',
'validate_peer_semantics.py': r'''#!/usr/bin/env python3
import json,sys
r=json.load(open(sys.argv[1])).get('validation_run',{}); peers=r.get('per_peer',r.get('per_peer_at_end',[])); ok=True; errs=[]
for p in peers:
 if p.get('run_starvation_recovery_success_count',0)>p.get('run_starvation_recovery_participation_count',0): ok=False; errs.append(p.get('node_id','?')+':success_gt_participation')
 if p.get('run_starvation_recovery_failure_count',0)>p.get('run_starvation_recovery_participation_count',0): ok=False; errs.append(p.get('node_id','?')+':failure_gt_participation')
print(json.dumps({'pass':ok,'peer_count':len(peers),'errors':errs},indent=2)); sys.exit(0 if ok else 1)
''',
'validate_peer_starvation_recovery.py': r'''#!/usr/bin/env python3
import json,sys
r=json.load(open(sys.argv[1])).get('validation_run',{}); ev=r.get('events',[]); ok=True; errs=[]
req=[e for e in ev if e.get('type')=='RECOVERY_REQUESTED' and e.get('trigger_kind')=='PEER_STARVATION']
for q in req:
 g=q.get('recovery_generation'); peer=q.get('trigger_peer_id') or q.get('peer_id'); ge=[e for e in ev if e.get('recovery_generation')==g]
 first=[e for e in ge if e.get('type')=='FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY']
 suc=[e for e in ge if e.get('type')=='RECOVERY_SUCCESS']
 if suc and (not first or first[0].get('peer_id')!=peer): ok=False; errs.append(f'generation {g}: success_without_target_first_valid')
 if len(suc)>1 or len([e for e in ge if e.get('type')=='RECOVERY_FAILURE'])>1: ok=False; errs.append(f'generation {g}: duplicate_terminal')
 if q.get('trigger_kind')!='PEER_STARVATION': ok=False
print(json.dumps({'pass':ok,'peer_starvation_recovery_requests':len(req),'errors':errs},indent=2)); sys.exit(0 if ok else 1)
''',
'validate_geometry_snapshot.py': r'''#!/usr/bin/env python3
import json,sys
r=json.load(open(sys.argv[1])).get('validation_run',{}); ok=r.get('snapshot_frozen') is True and 'geometry_at_end' in r and 'graph_diagnostics_at_end' in r
print(json.dumps({'pass':ok,'snapshot_frozen':r.get('snapshot_frozen'),'has_geometry_at_end':'geometry_at_end' in r},indent=2)); sys.exit(0 if ok else 1)
''',
'calculate_accuracy_report.py': r'''#!/usr/bin/env python3
import argparse,json,math
ap=argparse.ArgumentParser(); ap.add_argument('--ground-truth',required=True); ap.add_argument('--export',action='append',required=True); a=ap.parse_args()
gt=json.load(open(a.ground_truth)); obs=[]
for f in a.export:
 d=json.load(open(f)); obs += d.get('fused_range_observations',[])
pairs={}
for o in obs:
 p=tuple(sorted([o.get('observer_node_id',''),o.get('peer_node_id','')]))
 if all(p) and isinstance(o.get('distance_m'),(int,float)): pairs.setdefault('|'.join(p),[]).append(float(o['distance_m']))
errs=[]
for k,t in gt.get('pairs_m',{}).items():
 vals=pairs.get(k,[])
 if vals: errs.append(sum(vals)/len(vals)-float(t))
out={'physical_confidence':'COARSE','pair_count':len(errs),'directional_mae_m':sum(abs(x) for x in errs)/len(errs) if errs else None,'maximum_absolute_error_m':max(map(abs,errs)) if errs else None,'note':'informative; not a dev-12 blocker'}
print(json.dumps(out,indent=2))
''',
'validate_release_manifest.py': r'''#!/usr/bin/env python3
import json,sys
m=json.load(open(sys.argv[1])); checks=[m.get('release')=='dev-12',m.get('version')=='0.2.0-experimental.12',m.get('protocol_version')==2,m.get('ble_metric_rssi_at_1m_dbm')==-69.19,m.get('ble_metric_path_loss_exponent')==3.62,m.get('human_scanning_enabled') is False,m.get('screenshots_required_for_acceptance') is False,m.get('json_evidence_self_contained') is True]
ok=all(checks); print(json.dumps({'pass':ok,'checks':checks},indent=2)); sys.exit(0 if ok else 1)
''',
'build_acceptance_report.py': r'''#!/usr/bin/env python3
import argparse,json,subprocess,sys,tempfile,os
ap=argparse.ArgumentParser(); ap.add_argument('--device',action='append',default=[]); ap.add_argument('--out',default='acceptance_report.json'); a=ap.parse_args(); result={'release':'dev-12','devices':{},'pass':True}
for spec in a.device:
 name,path=spec.split('=',1); d=json.load(open(path)); r=d.get('validation_run',d); checks={'snapshot_frozen':r.get('snapshot_frozen') is True,'elapsed':r.get('elapsed_ms',0)>=300000,'duration_eligible':r.get('acceptance_duration_eligible') is True,'usable_metric':(r.get('usable_metric_range_uptime_percent') or 0)>=90,'geometry_2d':(r.get('geometry_2d_uptime_percent') or 0)>=90,'peer_expire':r.get('peer_expire_delta')==0,'recovery_budget':r.get('recovery_attempt_delta',99)<=3,'environment':r.get('environment_valid') is True}; passed=all(checks.values()); result['devices'][name]={'checks':checks,'pass':passed}; result['pass'] &= passed
open(a.out,'w').write(json.dumps(result,indent=2)+'\n'); print(json.dumps(result,indent=2)); sys.exit(0 if result['pass'] else 1)
''',
}
for name,body in validators.items(): write('validation/analysis/'+name, body)

# Deterministic semantic fixtures used by contract tests. These are validator-level
# fixtures, not fabricated physical evidence.
fixture_dir=ROOT/'validation/fixtures/dev12'; fixture_dir.mkdir(parents=True,exist_ok=True)
fixtures={
'isolated-gap-no-recovery.json': {'scenario':'isolated_5s_gap','expected':{'peer_health_state':'PEER_SPARSE','recovery_requested':False}},
'persistent-peer-starvation.json': {'scenario':'udp_active_ble_starved_6s','expected':{'peer_health_state':'PEER_STARVED','trigger_kind':'PEER_STARVATION','recovery_requested':True}},
'target-returns.json': {'scenario':'target_returns','events':[{'type':'RECOVERY_REQUESTED','recovery_generation':1,'trigger_kind':'PEER_STARVATION','trigger_peer_id':'P2','peer_id':'P2','seq':1,'wall_ms':1,'elapsed_from_run_start_ms':1},{'type':'FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY','recovery_generation':1,'trigger_kind':'PEER_STARVATION','peer_id':'P2','seq':2,'wall_ms':2,'elapsed_from_run_start_ms':2},{'type':'RECOVERY_SUCCESS','recovery_generation':1,'trigger_kind':'PEER_STARVATION','peer_id':'P2','seq':3,'wall_ms':3,'elapsed_from_run_start_ms':3}]},
'wrong-peer-returns.json': {'scenario':'wrong_peer_returns','expected':{'recovery_success':False,'target_peer':'P2','callback_peer':'P1'}},
'recovery-timeout.json': {'scenario':'target_never_returns','expected':{'terminal':'RECOVERY_FAILURE','invented_metric_range':False}},
'cooldown.json': {'scenario':'recovery_before_30s','expected':{'suppressed':True}},
'rolling-attempt-4.json': {'scenario':'attempt_4_inside_5min','expected':{'suppressed':True,'max_attempts':3}},
'full-cohort-priority.json': {'scenario':'peer_starvation_and_full_cohort_stall','expected':{'winner':'FULL_COHORT_STALL'}},
}
for n,d in fixtures.items(): (fixture_dir/n).write_text(json.dumps(d,indent=2)+'\n')

# Static contract catches accidental physics/gate relaxation and required dev12 source markers.
write('validation/android/check_dev12_peer_starvation_contract.py', r'''from pathlib import Path
root=Path(__file__).resolve().parents[2]
pol=(root/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleAcquisitionPolicy.kt').read_text()
mod=(root/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt').read_text()
app=(root/'apps/mobile/App.tsx').read_text(); ver=(root/'apps/mobile/src/version.ts').read_text()
need=[('PEER_STARVATION_PERSIST_MS = 6_000L',pol),('RecoveryTriggerKind.PEER_STARVATION',mod),('recoveryCallbackEligible',mod),('acceptance_duration_eligible',mod),('FLAG_KEEP_SCREEN_ON',mod),('screenshots_required',app),('0.2.0-experimental.12',ver)]
missing=[x for x,s in need if x not in s]; assert not missing,missing
frozen=[('MIN_SAMPLES_FOR_RANGE = 3',mod),('RANGE_FRESHNESS_MS = 5_000L',mod),('MIN_RESTART_COOLDOWN_MS = 30_000L',pol),('MAX_RECOVERY_ATTEMPTS_PER_5MIN = 3',pol)]
missing=[x for x,s in frozen if x not in s]; assert not missing,missing
print('PASS dev12 peer starvation/static truth contract')
''')

# Copy/advance workflows from proven dev11 matrix.
ci=read('.github/workflows/ci-exp11.yml')
ci=ci.replace('experimental.11','experimental.12').replace('exp11','exp12').replace('dev11','dev12').replace('DEV11','DEV12')
ci=ci.replace('reportVersion: 13','reportVersion: 14').replace('"versionCode": 11','"versionCode": 12')
ci=ci.replace('python3 validation/android/check_dev12_frozen_truth_contract.py', 'python3 validation/android/check_dev11_frozen_truth_contract.py\n          python3 validation/android/check_dev12_peer_starvation_contract.py')
write('.github/workflows/ci-exp12.yml',ci)

rel=read('.github/workflows/release-exp11.yml')
rel=rel.replace('experimental.11','experimental.12').replace('experimental11','experimental12').replace('exp11','exp12').replace('dev-11','dev-12').replace('dev11','dev12').replace('DEV11','DEV12')
rel=rel.replace('reportVersion: 13','reportVersion: 14').replace('"versionCode": 11','"versionCode": 12')
# Keep legacy frozen truth validator and add new dev12 contract.
rel=rel.replace('python3 validation/android/check_dev12_frozen_truth_contract.py', 'python3 validation/android/check_dev11_frozen_truth_contract.py\n          python3 validation/android/check_dev12_peer_starvation_contract.py')
# Replace dev11-specific docs/fixtures packaging with dev12 docs plus validators/fixtures zips while preserving existing compatibility artifacts.
rel=rel.replace('cp docs/ANDROID_DEV12_FINAL_ACCEPTANCE_RETEST.md dist/ANDROID_DEV12_FINAL_ACCEPTANCE_RETEST.md', 'cp docs/TESTING_DEV12.md dist/TESTING_DEV12.md')
rel=rel.replace('cp IMPLEMENTATION_PLAN_POST_DEV10_DEV12_RELEASE.md dist/IMPLEMENTATION_PLAN_POST_DEV10_DEV12_RELEASE.md', 'cp DEV12_FROZEN_TRUTH.md dist/DEV12_FROZEN_TRUTH.md')
rel=rel.replace('cp docs/ANDROID_DEV12_FINAL_ACCEPTANCE_RETEST.md dist/validation-kit/', 'cp docs/TESTING_DEV12.md dist/validation-kit/')
# Existing lines now point at dev12 fixture directory names after replacement and may not exist; normalize blocks.
rel=rel.replace('validation/fixtures/dev12/post-end-live-counter-drift-v2.json validation/fixtures/dev12/new-run-preserves-previous-completed.json', 'validation/fixtures/dev11/post-end-live-counter-drift-v2.json validation/fixtures/dev11/new-run-preserves-previous-completed.json')
rel=rel.replace('validation/fixtures/dev12/timeline-valid.json validation/fixtures/dev12/timeline-timestamp-inversion.json validation/fixtures/dev12/stalled-event-wrong-state.json validation/fixtures/dev12/duplicate-first-callback.json', 'validation/fixtures/dev11/timeline-valid.json validation/fixtures/dev11/timeline-timestamp-inversion.json validation/fixtures/dev11/stalled-event-wrong-state.json validation/fixtures/dev11/duplicate-first-callback.json')
rel=rel.replace('validation/fixtures/dev12/peer-lifetime-vs-run-scope.json', 'validation/fixtures/dev11/peer-lifetime-vs-run-scope.json')
rel=rel.replace('validation/fixtures/dev12/geometry-at-end-drift.json', 'validation/fixtures/dev11/geometry-at-end-drift.json')
# Ensure new validators are present in validation kit and dedicated zips.
needle='''          (cd dist/validation-kit && zip -r ../body-finder-validation-tools.zip .)\n          rm -rf dist/validation-kit\n'''
insert='''          cp validation/analysis/validate_dev12_hard_gates.py validation/analysis/validate_snapshot_immutability.py validation/analysis/validate_timeline_causality.py validation/analysis/validate_peer_semantics.py validation/analysis/validate_peer_starvation_recovery.py validation/analysis/validate_geometry_snapshot.py validation/analysis/calculate_accuracy_report.py validation/analysis/validate_release_manifest.py validation/analysis/build_acceptance_report.py dist/validation-kit/\n          (cd dist/validation-kit && zip -r ../body-finder-validation-tools.zip .)\n          cp dist/body-finder-validation-tools.zip dist/validators-dev12.zip\n          rm -rf dist/validation-kit\n          (cd validation/fixtures/dev12 && zip -r "$GITHUB_WORKSPACE/dist/fixtures-dev12.zip" .)\n'''
if needle not in rel: raise SystemExit('release workflow validation-kit anchor missing')
rel=rel.replace(needle,insert,1)
# Manifest: extend truth and rename schema to 12.
rel=rel.replace('"schema_version": 11,','"schema_version": 12,')
manifest_anchor='''            "android_api36_ble_yield_ms": 120000,\n            "human_scanning_enabled": false,'''
manifest_new='''            "android_api36_ble_yield_ms": 120000,\n            "peer_starvation_persist_ms": 6000,\n            "per_peer_starvation_recovery": true,\n            "peer_targeted_recovery_success": true,\n            "acceptance_minimum_ms": 300000,\n            "json_evidence_self_contained": true,\n            "screenshots_required_for_acceptance": false,\n            "human_scanning_enabled": false,'''
if manifest_anchor not in rel: raise SystemExit('release manifest anchor missing')
rel=rel.replace(manifest_anchor,manifest_new,1)
# Add explicit dev12 universal APK alias required by the implementation plan.
rel=rel.replace('          cp android/app/build/outputs/bundle/release/*.aab ../../dist/body-finder-ruview.aab\n          test -s ../../dist/body-finder-ruview-universal.apk', '          cp ../../dist/body-finder-ruview-universal.apk ../../dist/BodyFinder-dev12-universal.apk\n          cp android/app/build/outputs/bundle/release/*.aab ../../dist/body-finder-ruview.aab\n          test -s ../../dist/body-finder-ruview-universal.apk\n          test -s ../../dist/BodyFinder-dev12-universal.apk')
# Inject artifact inventory hashes into release-manifest before the final SHA256SUMS is generated.
manifest_step='''      - name: Generate SPDX SBOM
'''
manifest_inventory='''      - name: Add artifact inventory to release manifest
        shell: bash
        run: |
          python3 - <<'PY'
          import hashlib,json,pathlib
          d=pathlib.Path('dist'); p=d/'release-manifest.json'; m=json.load(open(p))
          arts=[]
          for f in sorted(x for x in d.iterdir() if x.is_file() and x.name not in {'release-manifest.json','SHA256SUMS'}):
              arts.append({'name':f.name,'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'size_bytes':f.stat().st_size})
          m['artifacts']=arts
          p.write_text(json.dumps(m,indent=2)+'\n')
          PY
      - name: Generate SPDX SBOM
'''
if manifest_step not in rel: raise SystemExit('SBOM anchor missing')
rel=rel.replace(manifest_step,manifest_inventory,1)
# Mandatory artifacts: use TESTING_DEV12 and plan; add validators+fixtures.
rel=rel.replace('ANDROID_DEV12_FINAL_ACCEPTANCE_RETEST.md IMPLEMENTATION_PLAN_POST_DEV10_DEV12_RELEASE.md', 'TESTING_DEV12.md DEV12_FROZEN_TRUTH.md')
rel=rel.replace('body-finder-ruview-universal.apk body-finder-ruview.aab', 'body-finder-ruview-universal.apk BodyFinder-dev12-universal.apk body-finder-ruview.aab')
rel=rel.replace('geometry-at-end-regression-fixtures.zip body-finder-validation-tools.zip', 'geometry-at-end-regression-fixtures.zip body-finder-validation-tools.zip validators-dev12.zip fixtures-dev12.zip')
rel=rel.replace("'ANDROID_DEV12_FINAL_ACCEPTANCE_RETEST.md','IMPLEMENTATION_PLAN_POST_DEV10_DEV12_RELEASE.md'", "'TESTING_DEV12.md','DEV12_FROZEN_TRUTH.md'")
rel=rel.replace("'body-finder-ruview-universal.apk','body-finder-ruview.aab'", "'body-finder-ruview-universal.apk','BodyFinder-dev12-universal.apk','body-finder-ruview.aab'")
rel=rel.replace("'geometry-at-end-regression-fixtures.zip','body-finder-validation-tools.zip'", "'geometry-at-end-regression-fixtures.zip','body-finder-validation-tools.zip','validators-dev12.zip','fixtures-dev12.zip'")
# Release notes explicitly remove screenshots requirement.
rel=rel.replace('Start with ANDROID_DEV12_FINAL_ACCEPTANCE_RETEST.md.', 'Start with TESTING_DEV12.md. Acceptance evidence is JSON-only; screenshots are not required.')
write('.github/workflows/release-exp12.yml',rel)

# Trigger files and plan are expected to be already present when bootstrap runs.
print('dev12 source patch applied successfully')
