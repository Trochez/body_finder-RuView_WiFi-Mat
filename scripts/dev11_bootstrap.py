#!/usr/bin/env python3
from pathlib import Path
import json
import re
import shutil
import textwrap

ROOT = Path(__file__).resolve().parents[1]

def read(path):
    return (ROOT / path).read_text(encoding='utf-8')

def write(path, content):
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding='utf-8')

def replace_once(path, old, new):
    s = read(path)
    if old not in s:
        raise SystemExit(f'missing expected text in {path}: {old[:120]!r}')
    write(path, s.replace(old, new, 1))

def regex_once(path, pattern, replacement, flags=re.S):
    s = read(path)
    out, count = re.subn(pattern, replacement, s, count=1, flags=flags)
    if count != 1:
        raise SystemExit(f'expected one regex match in {path}, got {count}: {pattern[:120]}')
    write(path, out)

# ---------------------------------------------------------------------------
# Version truth
# ---------------------------------------------------------------------------
write('apps/mobile/src/version.ts', """export const RELEASE = Object.freeze({
  build: '0.2.0-experimental.11',
  reportVersion: 13,
  versionCode: 11,
  releaseIteration: 'experimental.11',
  protocolVersion: 2,
  snapshotSchemaVersion: 2,
  humanScanningEnabled: false,
  humanLocalizationValidated: false,
  rescueUseValidated: false,
});
export const BUILD = RELEASE.build;
export const REPORT_VERSION = RELEASE.reportVersion;
export const HUMAN_SCANNING_ENABLED = RELEASE.humanScanningEnabled;
""")

app_json = json.loads(read('apps/mobile/app.json'))
app_json['expo']['android']['versionCode'] = 11
app_json['expo']['extra']['releaseIteration'] = 'experimental.11'
write('apps/mobile/app.json', json.dumps(app_json, indent=2, ensure_ascii=False) + '\n')

legacy = read('apps/android-legacy/app/build.gradle')
legacy = legacy.replace("versionCode 10; versionName '0.2.0-experimental.10'", "versionCode 11; versionName '0.2.0-experimental.11'")
write('apps/android-legacy/app/build.gradle', legacy)

# ---------------------------------------------------------------------------
# Recovery generation + causal timeline + peer telemetry semantics
# ---------------------------------------------------------------------------
policy_path = 'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleAcquisitionPolicy.kt'
policy = read(policy_path)
policy = policy.replace('Acquisition-only policy for experimental.9.', 'Acquisition-only policy for experimental.11.')
policy = policy.replace(
    '  private val recoveryAttemptWallMs = ConcurrentLinkedDeque<Long>()\n',
    '  private val recoveryAttemptWallMs = ConcurrentLinkedDeque<Long>()\n'
    '  private val recoveryGenerationCounter = AtomicLong(0)\n'
    '  @Volatile private var activeRecoveryGeneration: Long? = null\n'
    '  private val recoverySuccessGeneration = AtomicLong(0)\n'
    '  private val recoveryFailureGeneration = AtomicLong(0)\n'
)
policy = policy.replace(
    '    recoveryAttemptWallMs.clear()\n',
    '    recoveryAttemptWallMs.clear()\n'
    '    recoveryGenerationCounter.set(0)\n'
    '    activeRecoveryGeneration = null\n'
    '    recoverySuccessGeneration.set(0)\n'
    '    recoveryFailureGeneration.set(0)\n'
)
policy = policy.replace(
    '  fun lastStrategyReason(): String = lastStrategyReason\n',
    '  fun lastStrategyReason(): String = lastStrategyReason\n'
    '  fun activeRecoveryGeneration(): Long? = activeRecoveryGeneration\n'
    '  fun currentRecoveryGeneration(): Long = activeRecoveryGeneration ?: recoveryGenerationCounter.get()\n'
)
old_transition = '''  @Synchronized
  fun transition(next: BleAcquisitionStrategy, now: Long, reason: String) {
    if (strategy == next) return
    accumulateCurrentMode(now)
    strategy = next
    strategySinceWallMs = now
    lastStrategyReason = reason
    transitionCount++
    ValidationEventLog.record("ACQUISITION_STRATEGY_CHANGED", "$reason:${next.name}", now = now)
  }
'''
new_transition = '''  @Synchronized
  fun transition(next: BleAcquisitionStrategy, now: Long, reason: String) {
    if (strategy == next) return
    accumulateCurrentMode(now)
    strategy = next
    strategySinceWallMs = now
    lastStrategyReason = reason
    transitionCount++
    ValidationEventLog.record("ACQUISITION_STRATEGY_CHANGED", "$reason:${next.name}", now = now)
    if (next == BleAcquisitionStrategy.FILTERED_PRIMARY || next == BleAcquisitionStrategy.FAILED_SAFE) {
      activeRecoveryGeneration = null
    }
  }
'''
if old_transition not in policy: raise SystemExit('transition block not found')
policy = policy.replace(old_transition, new_transition, 1)
old_cohort = '''  @Synchronized
  fun updateCohortHealth(next: BodyFinderCohortHealth) {
    if (next == BodyFinderCohortHealth.BF_COHORT_STALLED && cohortHealth != BodyFinderCohortHealth.BF_COHORT_STALLED) {
      cohortStallCount++
      ValidationEventLog.record("BF_COHORT_STALLED", "GLOBAL_HEALTHY_BF_STALE", now = System.currentTimeMillis())
    }
    cohortHealth = next
  }
'''
new_cohort = '''  @Synchronized
  fun updateCohortHealth(next: BodyFinderCohortHealth, now: Long = System.currentTimeMillis()) {
    val previous = cohortHealth
    cohortHealth = next
    if (next == BodyFinderCohortHealth.BF_COHORT_STALLED && previous != BodyFinderCohortHealth.BF_COHORT_STALLED) {
      cohortStallCount++
      ValidationEventLog.record("BF_COHORT_STALLED", "GLOBAL_HEALTHY_BF_STALE", now = now)
    }
  }
'''
if old_cohort not in policy: raise SystemExit('cohort block not found')
policy = policy.replace(old_cohort, new_cohort, 1)
policy = policy.replace('ValidationEventLog.record("RECOVERY_SUPPRESSED_COOLDOWN", "MIN_RESTART_COOLDOWN")', 'ValidationEventLog.record("RECOVERY_SUPPRESSED_COOLDOWN", "MIN_RESTART_COOLDOWN", now = now)')
policy = policy.replace('ValidationEventLog.record("RECOVERY_SUPPRESSED_MAX_ATTEMPTS", "MAX_RECOVERY_ATTEMPTS_PER_5MIN")', 'ValidationEventLog.record("RECOVERY_SUPPRESSED_MAX_ATTEMPTS", "MAX_RECOVERY_ATTEMPTS_PER_5MIN", now = now)')
old_begin = '''  @Synchronized
  fun beginRecovery(now: Long, reason: String) {
    recoveryAttemptCountTotal++
    recoveryAttemptWallMs.addLast(now)
    ValidationEventLog.record("RECOVERY_REQUESTED", reason, now = now)
    lastRecoveryAttemptWallMs = now
    recoveryStartedWallMs = now
    transition(BleAcquisitionStrategy.UNFILTERED_RECOVERY, now, reason)
    cohortHealth = BodyFinderCohortHealth.BF_COHORT_RECOVERING
  }

  @Synchronized
  fun noteRecoverySuccess(now: Long) {
    val start = recoveryStartedWallMs
    if (start != null) lastRecoveryLatencyMs = max(0L, now - start)
    cohortRecoveryCount++
    ValidationEventLog.record("RECOVERY_SUCCESS", "FIRST_VALID_BF_CALLBACK", now = now)
    recoveryStartedWallMs = null
  }

  @Synchronized
  fun noteRecoveryFailure() {
    cohortRecoveryFailureCount++
    ValidationEventLog.record("RECOVERY_FAILURE", "RECOVERY_WINDOW_EXPIRED")
    recoveryStartedWallMs = null
  }
'''
new_begin = '''  @Synchronized
  fun beginRecovery(now: Long, reason: String) {
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
'''
if old_begin not in policy: raise SystemExit('recovery block not found')
policy = policy.replace(old_begin, new_begin, 1)
policy = policy.replace(
'''internal data class BleAcquisitionCounterSnapshot(
  val callbackCount: Long,
  val validCallbackCount: Long,
  val invalidCallbackCount: Long,
  val gapGt1sCount: Long,
  val gapGt2sCount: Long,
  val gapGt5sCount: Long,
  val gapGt10sCount: Long,
  val filteredCallbackCount: Long = 0,
  val unfilteredCallbackCount: Long = 0,
)''',
'''internal data class BleAcquisitionCounterSnapshot(
  val callbackCount: Long,
  val validCallbackCount: Long,
  val invalidCallbackCount: Long,
  val gapGt1sCount: Long,
  val gapGt2sCount: Long,
  val gapGt5sCount: Long,
  val gapGt10sCount: Long,
  val filteredCallbackCount: Long = 0,
  val unfilteredCallbackCount: Long = 0,
  val recoveryParticipationCount: Long = 0,
  val firstCallbackAfterRecoveryCount: Long = 0,
)''')
policy = policy.replace(
'''  private val recentIntervalsMs = ConcurrentLinkedDeque<Long>()
  private val peerRecoveryCount = AtomicLong(0)
  private val lastPeerRecoveryLatencyMs = AtomicLong(0)
''',
'''  private val recentIntervalsMs = ConcurrentLinkedDeque<Long>()
  private val recoveryParticipationCount = AtomicLong(0)
  private val firstCallbackAfterRecoveryCount = AtomicLong(0)
  private val lastRecoveryGenerationSeen = AtomicLong(0)
  private val lastFirstValidRecoveryGeneration = AtomicLong(0)
  private val lastRecoveryCallbackLatencyMs = AtomicLong(0)
''')
policy = policy.replace(
'''  fun record(now: Long, validRssi: Boolean, strategy: BleAcquisitionStrategy = BleAcquisitionPolicy.currentStrategy()) {
    firstCallbackWallMs.compareAndSet(0L, now)
''',
'''  private fun markGeneration(slot: AtomicLong, generation: Long): Boolean {
    while (true) {
      val previous = slot.get()
      if (previous == generation) return false
      if (slot.compareAndSet(previous, generation)) return true
    }
  }

  fun record(now: Long, validRssi: Boolean, strategy: BleAcquisitionStrategy = BleAcquisitionPolicy.currentStrategy()) {
    firstCallbackWallMs.compareAndSet(0L, now)
''')
policy = policy.replace(
'''    if (validRssi) {
      validCallbackCount.incrementAndGet()
      lastValidCallbackStrategy = strategy.name
    } else invalidCallbackCount.incrementAndGet()
    if (previous <= 0L) return
''',
'''    if (validRssi) {
      validCallbackCount.incrementAndGet()
      lastValidCallbackStrategy = strategy.name
      if (strategy == BleAcquisitionStrategy.UNFILTERED_RECOVERY) {
        val generation = BleAcquisitionPolicy.activeRecoveryGeneration()
        if (generation != null) {
          if (markGeneration(lastRecoveryGenerationSeen, generation)) recoveryParticipationCount.incrementAndGet()
          if (markGeneration(lastFirstValidRecoveryGeneration, generation)) firstCallbackAfterRecoveryCount.incrementAndGet()
          val started = BleAcquisitionPolicy.recoveryStartedMs()
          if (started != null) lastRecoveryCallbackLatencyMs.set(max(0L, now - started))
        }
      }
    } else invalidCallbackCount.incrementAndGet()
    if (previous <= 0L) return
''')
policy = policy.replace(
'    if (interval > BleAcquisitionPolicy.GAP_5S_MS) { gapGt5sCount.incrementAndGet(); peerRecoveryCount.incrementAndGet(); lastPeerRecoveryLatencyMs.set(interval) }',
'    if (interval > BleAcquisitionPolicy.GAP_5S_MS) gapGt5sCount.incrementAndGet()')
policy = policy.replace(
'''    filteredCallbackCount.get(), unfilteredCallbackCount.get(),
  )''',
'''    filteredCallbackCount.get(), unfilteredCallbackCount.get(),
    recoveryParticipationCount.get(), firstCallbackAfterRecoveryCount.get(),
  )''')
policy = policy.replace('fun delta(current: Long, previous: Long?): Long = (current - (previous ?: current)).coerceAtLeast(0L)', 'fun delta(current: Long, previous: Long?): Long = (current - (previous ?: 0L)).coerceAtLeast(0L)')
policy = policy.replace(
'''      .put("callback_count", snap.callbackCount)
      .put("valid_rssi_callback_count", snap.validCallbackCount)
      .put("invalid_rssi_callback_count", snap.invalidCallbackCount)''',
'''      .put("callback_count", snap.callbackCount)
      .put("lifetime_callback_count", snap.callbackCount)
      .put("valid_rssi_callback_count", snap.validCallbackCount)
      .put("invalid_rssi_callback_count", snap.invalidCallbackCount)''')
policy = policy.replace(
'''      .put("gap_gt_1s_count", snap.gapGt1sCount)
      .put("gap_gt_2s_count", snap.gapGt2sCount)
      .put("gap_gt_5s_count", snap.gapGt5sCount)
      .put("gap_gt_10s_count", snap.gapGt10sCount)''',
'''      .put("gap_gt_1s_count", snap.gapGt1sCount)
      .put("gap_gt_2s_count", snap.gapGt2sCount)
      .put("gap_gt_5s_count", snap.gapGt5sCount)
      .put("gap_gt_10s_count", snap.gapGt10sCount)
      .put("lifetime_gap_gt_1s_count", snap.gapGt1sCount)
      .put("lifetime_gap_gt_2s_count", snap.gapGt2sCount)
      .put("lifetime_gap_gt_5s_count", snap.gapGt5sCount)
      .put("lifetime_gap_gt_10s_count", snap.gapGt10sCount)''')
policy = policy.replace(
'''      .put("run_callbacks_filtered_delta", delta(snap.filteredCallbackCount, baseline?.filteredCallbackCount))
      .put("run_callbacks_unfiltered_delta", delta(snap.unfilteredCallbackCount, baseline?.unfilteredCallbackCount))
      .put("peer_stall_count", snap.gapGt5sCount)
      .put("peer_recovery_count", peerRecoveryCount.get())
      .put("peer_recovery_latency_ms", lastPeerRecoveryLatencyMs.get().takeIf { it > 0 } ?: JSONObject.NULL)''',
'''      .put("run_filtered_callback_delta", delta(snap.filteredCallbackCount, baseline?.filteredCallbackCount))
      .put("run_unfiltered_callback_delta", delta(snap.unfilteredCallbackCount, baseline?.unfilteredCallbackCount))
      .put("run_callbacks_filtered_delta", delta(snap.filteredCallbackCount, baseline?.filteredCallbackCount))
      .put("run_callbacks_unfiltered_delta", delta(snap.unfilteredCallbackCount, baseline?.unfilteredCallbackCount))
      .put("run_recovery_participation_count", delta(snap.recoveryParticipationCount, baseline?.recoveryParticipationCount))
      .put("run_first_callback_after_recovery_count", delta(snap.firstCallbackAfterRecoveryCount, baseline?.firstCallbackAfterRecoveryCount))
      .put("last_recovery_generation_seen", lastRecoveryGenerationSeen.get().takeIf { it > 0 } ?: JSONObject.NULL)
      .put("last_recovery_callback_latency_ms", lastRecoveryCallbackLatencyMs.get().takeIf { it > 0 } ?: JSONObject.NULL)
      .put("peer_stall_count", snap.gapGt5sCount)
      .put("peer_recovery_count", snap.recoveryParticipationCount)
      .put("peer_recovery_semantics", "RECOVERY_GENERATION_PARTICIPATION")
      .put("peer_recovery_latency_ms", lastRecoveryCallbackLatencyMs.get().takeIf { it > 0 } ?: JSONObject.NULL)''')
write(policy_path, policy)

# Deterministic, monotonic event log with generation provenance and exactly-once first callback.
write('apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/ValidationEventLog.kt', r'''package com.trochez.bodyfindernative

import android.os.Build
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.ConcurrentLinkedDeque
import java.util.concurrent.atomic.AtomicLong
import kotlin.math.max

internal data class ValidationEvent(
  val seq: Long,
  val wallMs: Long,
  val type: String,
  val reason: String,
  val strategy: String,
  val cohort: String,
  val rangingState: String,
  val yieldActive: Boolean,
  val recoveryGeneration: Long?,
)

internal object ValidationEventLog {
  private const val MAX_RUNTIME = 512
  private const val MAX_RUN = 256
  private val seq = AtomicLong(0)
  private val q = ConcurrentLinkedDeque<ValidationEvent>()
  private var lastWallMs: Long = 0
  private var firstCallbackRecordedGeneration: Long = 0

  @Synchronized
  fun reset() {
    seq.set(0)
    q.clear()
    lastWallMs = 0
    firstCallbackRecordedGeneration = 0
  }

  fun currentSeq(): Long = seq.get()

  @Synchronized
  fun record(type: String, reason: String = "", now: Long = System.currentTimeMillis()) {
    val generation = BleAcquisitionPolicy.activeRecoveryGeneration()
    if (type == "FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY") {
      val g = generation ?: return
      if (firstCallbackRecordedGeneration == g) return
      firstCallbackRecordedGeneration = g
    }
    val eventNow = max(now, lastWallMs)
    lastWallMs = eventNow
    val rs = if (Build.VERSION.SDK_INT >= 36) SystemRangingApi36.stateLabel() else "UNSUPPORTED"
    val y = Build.VERSION.SDK_INT >= 36 && SystemRangingApi36.isBleYieldActive(eventNow)
    q.addLast(
      ValidationEvent(
        seq.incrementAndGet(), eventNow, type, reason,
        BleAcquisitionPolicy.currentStrategy().name,
        BleAcquisitionPolicy.currentCohortHealth().name,
        rs, y, generation,
      )
    )
    while (q.size > MAX_RUNTIME) q.pollFirst()
  }

  @Synchronized
  fun snapshotSince(after: Long, start: Long): JSONObject {
    val all = q.filter { it.seq > after }
    val kept = if (all.size > MAX_RUN) all.takeLast(MAX_RUN) else all
    val a = JSONArray()
    kept.forEach { e ->
      a.put(
        JSONObject()
          .put("seq", e.seq)
          .put("wall_ms", e.wallMs)
          .put("elapsed_ms", max(0, e.wallMs - start))
          .put("elapsed_from_run_start_ms", max(0, e.wallMs - start))
          .put("type", e.type)
          .put("reason", e.reason)
          .put("logical_strategy", e.strategy)
          .put("cohort_health", e.cohort)
          .put("system_ranging_state", e.rangingState)
          .put("ranging_yield_active", e.yieldActive)
          .put("recovery_generation", e.recoveryGeneration ?: JSONObject.NULL)
      )
    }
    return JSONObject()
      .put("events", a)
      .put("event_timeline_total_count", all.size)
      .put("event_timeline_truncated", all.size > MAX_RUN)
  }
}
''')

# ---------------------------------------------------------------------------
# Native immutable snapshot history v2 and geometry/fusion truth freeze
# ---------------------------------------------------------------------------
native_path = 'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt'
native = read(native_path)
validation_runtime = r'''private data class CompletedValidationRun(val runId: String, val snapshotJson: String)

private object ValidationRuntime {
  const val MAX_COMPLETED_VALIDATION_RUNS = 5
  @Volatile var runId: String? = null
  @Volatile var startedWallMs: Long? = null
  @Volatile var endedWallMs: Long? = null
  @Volatile var appVisibility: String = "UNKNOWN"
  @Volatile var geometryState: String = "UNKNOWN"
  @Volatile private var lastObserveWallMs: Long? = null
  @Volatile private var peerFullUptimeMs: Long = 0
  @Volatile private var rangeEvidenceUptimeMs: Long = 0
  @Volatile private var freshMetricRangeUptimeMs: Long = 0
  @Volatile private var usableMetricRangeUptimeMs: Long = 0
  @Volatile private var holdoverMetricUptimeMs: Long = 0
  @Volatile private var geometry2dUptimeMs: Long = 0
  @Volatile private var baselinePeerExpire: Long = 0
  @Volatile private var baselineRebind: Long = 0
  @Volatile private var baselineScanRestart: Long = 0
  @Volatile private var baselineTx: Long = 0
  @Volatile private var baselineRx: Long = 0
  @Volatile private var environmentViolationCount: Long = 0
  @Volatile private var firstEnvironmentViolationWallMs: Long? = null
  @Volatile private var environmentViolationTypes: String = ""
  @Volatile private var baselineStrategyTransitions: Long = 0
  @Volatile private var baselineCohortStalls: Long = 0
  @Volatile private var baselineCohortRecoveries: Long = 0
  @Volatile private var baselineCohortRecoveryFailures: Long = 0
  @Volatile private var baselineRecoveryAttempts: Long = 0
  @Volatile private var baselineRestartSuppressed: Long = 0
  @Volatile private var baselineRangingYield: Long = 0
  @Volatile private var baselineRangingReal: Long = 0
  @Volatile private var baselineRangingClose: Long = 0
  @Volatile private var baselineEventSeq: Long = 0
  @Volatile private var validationTruthJson: String = "{}"
  @Volatile private var selectedCompletedRunId: String? = null
  private val completedRuns = java.util.ArrayDeque<CompletedValidationRun>()

  @Synchronized
  fun start(now: Long, peerExpire: Long, rebind: Long, scanRestart: Long, tx: Long, rx: Long): String {
    if (runId != null && endedWallMs == null) return runId!!
    val id = UUID.randomUUID().toString()
    runId = id
    startedWallMs = now
    endedWallMs = null
    lastObserveWallMs = now
    peerFullUptimeMs = 0
    rangeEvidenceUptimeMs = 0
    freshMetricRangeUptimeMs = 0
    usableMetricRangeUptimeMs = 0
    holdoverMetricUptimeMs = 0
    geometry2dUptimeMs = 0
    baselinePeerExpire = peerExpire
    baselineRebind = rebind
    baselineScanRestart = scanRestart
    baselineTx = tx
    baselineRx = rx
    environmentViolationCount = 0
    firstEnvironmentViolationWallMs = null
    environmentViolationTypes = ""
    baselineStrategyTransitions = BleAcquisitionPolicy.transitionCount()
    baselineCohortStalls = BleAcquisitionPolicy.cohortStallCount()
    baselineCohortRecoveries = BleAcquisitionPolicy.cohortRecoveryCount()
    baselineCohortRecoveryFailures = BleAcquisitionPolicy.cohortRecoveryFailureCount()
    baselineRecoveryAttempts = BleAcquisitionPolicy.recoveryAttemptCount()
    baselineRestartSuppressed = BleAcquisitionPolicy.restartSuppressedCount()
    val r = if (Build.VERSION.SDK_INT >= 36) SystemRangingApi36.counterSnapshot() else SystemRangingCounterSnapshot(0, 0, 0)
    baselineRangingYield = r.yieldTransitions
    baselineRangingReal = r.realDistanceResults
    baselineRangingClose = r.closeFailures
    baselineEventSeq = ValidationEventLog.currentSeq()
    validationTruthJson = "{}"
    ValidationEventLog.record("VALIDATION_RUN_STARTED", id, now = now)
    return id
  }

  @Synchronized
  fun observe(now: Long, activePeerCount: Int, evidenceReadyPeerCount: Int, freshMetricReadyPeerCount: Int, usableMetricReadyPeerCount: Int) {
    if (runId == null || endedWallMs != null) return
    val previous = lastObserveWallMs ?: now
    val dt = (now - previous).coerceIn(0L, 5_000L)
    if (activePeerCount >= 2) peerFullUptimeMs += dt
    if (evidenceReadyPeerCount >= 2) rangeEvidenceUptimeMs += dt
    if (freshMetricReadyPeerCount >= 2) freshMetricRangeUptimeMs += dt
    if (usableMetricReadyPeerCount >= 2) usableMetricRangeUptimeMs += dt
    if (usableMetricReadyPeerCount >= 2 && freshMetricReadyPeerCount < 2) holdoverMetricUptimeMs += dt
    if (geometryState == "GEOMETRY_2D") geometry2dUptimeMs += dt
    lastObserveWallMs = now
  }

  @Synchronized
  fun updateTruth(json: String) {
    if (runId == null || endedWallMs != null) return
    validationTruthJson = try { JSONObject(json).toString() } catch (_: Throwable) { "{}" }
  }

  @Synchronized
  fun end(now: Long, peerExpire: Long, rebind: Long, scanRestart: Long, tx: Long, rx: Long, acquisitionState: JSONObject, perPeer: JSONArray, systemRanging: JSONObject) {
    val id = runId ?: return
    if (endedWallMs != null) return
    endedWallMs = now
    lastObserveWallMs = now
    ValidationEventLog.record("VALIDATION_RUN_ENDED", id, now = now)
    val base = liveDiagnostics(now, peerExpire, rebind, scanRestart, tx, rx)
    val timeline = ValidationEventLog.snapshotSince(baselineEventSeq, startedWallMs ?: now)
    val events = timeline.optJSONArray("events") ?: JSONArray()
    var stallsDuringYield = 0
    for (i in 0 until events.length()) {
      val e = events.optJSONObject(i) ?: continue
      if (e.optString("type") == "BF_COHORT_STALLED" && e.optBoolean("ranging_yield_active")) stallsDuringYield++
    }
    val truth = try { JSONObject(validationTruthJson) } catch (_: Throwable) { JSONObject() }
    val environment = JSONObject()
      .put("valid", environmentViolationCount == 0L)
      .put("violation_count", environmentViolationCount)
      .put("first_violation_wall_ms", firstEnvironmentViolationWallMs ?: JSONObject.NULL)
      .put("violation_types", if (environmentViolationTypes.isBlank()) JSONArray() else JSONArray(environmentViolationTypes.split(',')))
    val counters = JSONObject()
      .put("peer_expire_delta", base.optLong("peer_expire_delta"))
      .put("address_rebind_delta", base.optLong("address_rebind_delta"))
      .put("scan_restart_delta", base.optLong("scan_restart_delta"))
      .put("tx_packets_delta", base.optLong("tx_packets_delta"))
      .put("rx_packets_delta", base.optLong("rx_packets_delta"))
      .put("recovery_attempt_delta", base.optLong("recovery_attempt_delta"))
      .put("cohort_stall_delta", base.optLong("cohort_stall_delta"))
    base
      .put("snapshot_frozen", true)
      .put("snapshot_schema_version", 2)
      .put("environment", environment)
      .put("validation_counters", counters)
      .put("acquisition_state_at_end", acquisitionState)
      .put("per_peer_at_end", perPeer)
      .put("per_peer", perPeer)
      .put("system_ranging_at_end", systemRanging)
      .put("events", events)
      .put("event_timeline_total_count", timeline.optInt("event_timeline_total_count"))
      .put("event_timeline_truncated", timeline.optBoolean("event_timeline_truncated"))
      .put("cohort_stall_while_ranging_yield_count", stallsDuringYield)
      .put("geometry_at_end", truth.opt("geometry") ?: JSONObject.NULL)
      .put("locally_computed_geometry_at_end", truth.opt("locally_computed_geometry") ?: JSONObject.NULL)
      .put("fused_range_observations_at_end", truth.opt("fused_range_observations") ?: JSONArray())
      .put("graph_diagnostics_at_end", truth.opt("graph_diagnostics") ?: JSONObject.NULL)
      .put("reciprocal_fusion_at_end", truth.opt("reciprocal_fusion") ?: JSONObject.NULL)
      .put("measurement_health_at_end", truth.opt("measurement_health") ?: JSONObject.NULL)
    val frozen = CompletedValidationRun(id, base.toString())
    completedRuns.addLast(frozen)
    while (completedRuns.size > MAX_COMPLETED_VALIDATION_RUNS) completedRuns.removeFirst()
    selectedCompletedRunId = id
  }

  @Synchronized
  fun updateGeometry(state: String) { geometryState = state }

  @Synchronized
  fun recordEnvironmentViolation(now: Long, issues: List<String>) {
    if (runId == null || endedWallMs != null || issues.isEmpty()) return
    environmentViolationCount++
    if (firstEnvironmentViolationWallMs == null) firstEnvironmentViolationWallMs = now
    environmentViolationTypes = (environmentViolationTypes.split(',').filter { it.isNotBlank() } + issues).distinct().joinToString(",")
  }

  private fun liveDiagnostics(now: Long, peerExpire: Long, rebind: Long, scanRestart: Long, tx: Long, rx: Long): JSONObject {
    val start = startedWallMs
    val effectiveEnd = endedWallMs ?: now
    val elapsed = if (start == null) 0L else max(0L, effectiveEnd - start)
    fun pct(value: Long): Any = if (elapsed <= 0) JSONObject.NULL else (100.0 * value / elapsed.toDouble())
    return JSONObject()
      .put("active", runId != null && endedWallMs == null)
      .put("run_id", runId ?: JSONObject.NULL)
      .put("started_wall_ms", start ?: JSONObject.NULL)
      .put("ended_wall_ms", endedWallMs ?: JSONObject.NULL)
      .put("snapshot_wall_ms", effectiveEnd)
      .put("snapshot_elapsed_ms", elapsed)
      .put("elapsed_ms", elapsed)
      .put("app_visibility", appVisibility)
      .put("current_geometry_state", geometryState)
      .put("peer_expire_delta", (peerExpire - baselinePeerExpire).coerceAtLeast(0))
      .put("address_rebind_delta", (rebind - baselineRebind).coerceAtLeast(0))
      .put("scan_restart_delta", (scanRestart - baselineScanRestart).coerceAtLeast(0))
      .put("tx_packets_delta", (tx - baselineTx).coerceAtLeast(0))
      .put("rx_packets_delta", (rx - baselineRx).coerceAtLeast(0))
      .put("all_peer_uptime_percent", pct(peerFullUptimeMs))
      .put("ble_evidence_uptime_percent", pct(rangeEvidenceUptimeMs))
      .put("fresh_metric_range_uptime_percent", pct(freshMetricRangeUptimeMs))
      .put("usable_metric_range_uptime_percent", pct(usableMetricRangeUptimeMs))
      .put("holdover_metric_uptime_percent", pct(holdoverMetricUptimeMs))
      .put("metric_range_uptime_percent", pct(usableMetricRangeUptimeMs))
      .put("geometry_2d_uptime_percent", pct(geometry2dUptimeMs))
      .put("environment_valid", environmentViolationCount == 0L)
      .put("environment_violation_count", environmentViolationCount)
      .put("first_environment_violation_wall_ms", firstEnvironmentViolationWallMs ?: JSONObject.NULL)
      .put("environment_violation_types", if (environmentViolationTypes.isBlank()) JSONArray() else JSONArray(environmentViolationTypes.split(',')))
      .put("strategy_transition_delta", (BleAcquisitionPolicy.transitionCount() - baselineStrategyTransitions).coerceAtLeast(0))
      .put("cohort_stall_delta", (BleAcquisitionPolicy.cohortStallCount() - baselineCohortStalls).coerceAtLeast(0))
      .put("cohort_recovery_delta", (BleAcquisitionPolicy.cohortRecoveryCount() - baselineCohortRecoveries).coerceAtLeast(0))
      .put("cohort_recovery_failure_delta", (BleAcquisitionPolicy.cohortRecoveryFailureCount() - baselineCohortRecoveryFailures).coerceAtLeast(0))
      .put("recovery_attempt_delta", (BleAcquisitionPolicy.recoveryAttemptCount() - baselineRecoveryAttempts).coerceAtLeast(0))
      .put("restart_suppressed_delta", (BleAcquisitionPolicy.restartSuppressedCount() - baselineRestartSuppressed).coerceAtLeast(0))
      .put("ranging_yield_transition_delta", ((if (Build.VERSION.SDK_INT >= 36) SystemRangingApi36.counterSnapshot().yieldTransitions else 0) - baselineRangingYield).coerceAtLeast(0))
      .put("ranging_real_result_delta", ((if (Build.VERSION.SDK_INT >= 36) SystemRangingApi36.counterSnapshot().realDistanceResults else 0) - baselineRangingReal).coerceAtLeast(0))
      .put("ranging_close_failure_delta", ((if (Build.VERSION.SDK_INT >= 36) SystemRangingApi36.counterSnapshot().closeFailures else 0) - baselineRangingClose).coerceAtLeast(0))
      .put("snapshot_frozen", false)
      .put("snapshot_schema_version", 2)
  }

  @Synchronized
  fun diagnostics(now: Long, peerExpire: Long, rebind: Long, scanRestart: Long, tx: Long, rx: Long): JSONObject {
    if (runId != null && endedWallMs == null) return liveDiagnostics(now, peerExpire, rebind, scanRestart, tx, rx)
    val selected = selectedCompletedRunId?.let { wanted -> completedRuns.firstOrNull { it.runId == wanted } }
      ?: completedRuns.lastOrNull()
    return selected?.let { JSONObject(it.snapshotJson) } ?: liveDiagnostics(now, peerExpire, rebind, scanRestart, tx, rx)
  }

  @Synchronized
  fun completedRunsSummary(): JSONArray {
    val out = JSONArray()
    completedRuns.forEach { run ->
      val j = JSONObject(run.snapshotJson)
      out.put(JSONObject()
        .put("run_id", run.runId)
        .put("started_wall_ms", j.opt("started_wall_ms"))
        .put("ended_wall_ms", j.opt("ended_wall_ms"))
        .put("elapsed_ms", j.optLong("elapsed_ms"))
        .put("snapshot_frozen", j.optBoolean("snapshot_frozen"))
        .put("snapshot_schema_version", j.optInt("snapshot_schema_version")))
    }
    return out
  }

  @Synchronized
  fun selectRun(id: String): Boolean {
    if (runId != null && endedWallMs == null) return false
    if (completedRuns.none { it.runId == id }) return false
    selectedCompletedRunId = id
    return true
  }

  @Synchronized fun selectedRunId(): String? = selectedCompletedRunId ?: completedRuns.lastOrNull()?.runId
}

private object FabricRuntime {'''
new_native, n = re.subn(r'private object ValidationRuntime \{.*?\n\}\n\nprivate object FabricRuntime \{', validation_runtime, native, count=1, flags=re.S)
if n != 1: raise SystemExit(f'ValidationRuntime replacement failed: {n}')
native = new_native
native = native.replace('BleAcquisitionPolicy.updateCohortHealth(cohort)', 'BleAcquisitionPolicy.updateCohortHealth(cohort, now)')
native = native.replace('if(BleAcquisitionPolicy.currentStrategy()==BleAcquisitionStrategy.UNFILTERED_RECOVERY) ValidationEventLog.record("FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY","BODY_FINDER_CALLBACK",now=now)\n', '')
native = native.replace(
    '    val validRssi = BleRangeEstimator.isValidBleRssi(result.rssi.toDouble())\n    FabricRuntime.acquisitionStatsByIdentity.computeIfAbsent(id) { BleAcquisitionStats() }.record(now, validRssi, BleAcquisitionPolicy.currentStrategy())',
    '    val validRssi = BleRangeEstimator.isValidBleRssi(result.rssi.toDouble())\n    if (validRssi && BleAcquisitionPolicy.currentStrategy() == BleAcquisitionStrategy.UNFILTERED_RECOVERY) ValidationEventLog.record("FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY", "BODY_FINDER_CALLBACK", now = now)\n    FabricRuntime.acquisitionStatsByIdentity.computeIfAbsent(id) { BleAcquisitionStats() }.record(now, validRssi, BleAcquisitionPolicy.currentStrategy())'
)
native = native.replace('BleAcquisitionPolicy.noteRecoveryFailure()\n          restartScannerWithStrategy(now, BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE, "RECOVERY_WINDOW_EXPIRED")', 'BleAcquisitionPolicy.noteRecoveryFailure(now)\n          restartScannerWithStrategy(now, BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE, "RECOVERY_WINDOW_EXPIRED")')
native = native.replace(
'''    Function("updateGeometryState") { geometryState: String ->
      ValidationRuntime.updateGeometry(geometryState)
      true
    }
''',
'''    Function("updateGeometryState") { geometryState: String ->
      ValidationRuntime.updateGeometry(geometryState)
      true
    }
    Function("updateValidationTruthJson") { truthJson: String ->
      ValidationRuntime.updateTruth(truthJson)
      true
    }
''')
native = native.replace(
'''    Function("getValidationRunJson") {
      val ctx = appContext.reactContext ?: return@Function "{}"
      validationRunDiagnostics(ctx).toString()
    }
''',
'''    Function("getValidationRunJson") {
      val ctx = appContext.reactContext ?: return@Function "{}"
      validationRunDiagnostics(ctx).toString()
    }
    Function("getCompletedValidationRunsSummaryJson") {
      ValidationRuntime.completedRunsSummary().toString()
    }
    Function("selectValidationRun") { selectedRunId: String ->
      ValidationRuntime.selectRun(selectedRunId)
    }
''')
old_diag_return = '''    return JSONObject()
      .put("ble_diagnostics", bleDiagnostics(ctx, now))
      .put("fabric_diagnostics", fabricDiagnostics(now))
      .put("lifecycle_diagnostics", lifecycleDiagnostics(ctx))
      .put("validation_run", validationRunDiagnostics(ctx, now))'''
new_diag_return = '''    return JSONObject()
      .put("ble_diagnostics", bleDiagnostics(ctx, now))
      .put("fabric_diagnostics", fabricDiagnostics(now))
      .put("lifecycle_diagnostics", lifecycleDiagnostics(ctx))
      .put("selected_validation_run_id", ValidationRuntime.selectedRunId() ?: JSONObject.NULL)
      .put("completed_validation_runs_summary", ValidationRuntime.completedRunsSummary())
      .put("validation_run", validationRunDiagnostics(ctx, now))'''
if old_diag_return not in native: raise SystemExit('outer diagnostics return not found')
native = native.replace(old_diag_return, new_diag_return, 1)
write(native_path, native)

# Native TS surface.
index_path = 'apps/mobile/modules/body-finder-native/index.ts'
idx = read(index_path)
idx = idx.replace('  updateGeometryState(geometryState: string): boolean;\n', '  updateGeometryState(geometryState: string): boolean;\n  updateValidationTruthJson(truthJson: string): boolean;\n')
idx = idx.replace('  getValidationRunJson(): string;\n', '  getValidationRunJson(): string;\n  getCompletedValidationRunsSummaryJson(): string;\n  selectValidationRun(runId: string): boolean;\n')
write(index_path, idx)

# ---------------------------------------------------------------------------
# React Native UI: version truth, geometry freeze feed, history selection,
# double-tap lock, explicit selected-run export.
# ---------------------------------------------------------------------------
app_path = 'apps/mobile/App.tsx'
app = read(app_path)
app = app.replace("import { applyReciprocalFusion } from './src/rangeFusion';\n\nconst BUILD = '0.2.0-experimental.10';\nconst REPORT_VERSION = 12;\nconst HUMAN_SCANNING_ENABLED = false;", "import { applyReciprocalFusion } from './src/rangeFusion';\nimport { BUILD, REPORT_VERSION, HUMAN_SCANNING_ENABLED, RELEASE } from './src/version';")
app = app.replace('experimental.10', 'experimental.11').replace('experimental.9', 'experimental.11')
app = app.replace("  const [validationRun, setValidationRun] = useState<any>(null);\n  const visualFrame", "  const [validationRun, setValidationRun] = useState<any>(null);\n  const [validationNotice, setValidationNotice] = useState<string | null>(null);\n  const validationActionLock = useRef(false);\n  const visualFrame")
needle = "  useEffect(() => { try { BodyFinderNative.updateGeometryState(geometryState); } catch {} }, [geometryState]);\n"
insert = needle + "\n  const validationTruth = useMemo(() => ({\n    geometry,\n    locally_computed_geometry: computedGeometry,\n    fused_range_observations: geometryNodes.flatMap(node => node.ranges ?? []),\n    graph_diagnostics: graphDiagnostics,\n    reciprocal_fusion: fused.diagnostics,\n    measurement_health: {\n      health: graphDiagnostics.measurement_health,\n      physical_confidence: graphDiagnostics.physical_confidence,\n      fresh_metric_edge_count: graphDiagnostics.fresh_metric_edge_count,\n      holdover_metric_edge_count: graphDiagnostics.holdover_metric_edge_count,\n      geometry_temporal_quality: graphDiagnostics.geometry_temporal_quality,\n    },\n  }), [geometry, computedGeometry, geometryNodes, graphDiagnostics, fused.diagnostics]);\n\n  useEffect(() => {\n    try { BodyFinderNative.updateValidationTruthJson(JSON.stringify(validationTruth)); } catch {}\n  }, [validationTruth]);\n"
if needle not in app: raise SystemExit('geometry effect not found')
app = app.replace(needle, insert, 1)
old_toggle = re.search(r'  function toggleValidationRun\(\) \{.*?\n  \}\n\n  async function share\(\)', app, re.S)
if not old_toggle: raise SystemExit('toggle function not found')
new_toggle = r'''  function refreshValidationState() {
    const fresh = JSON.parse(BodyFinderNative.getDiagnosticsJson());
    setDiagnostics(fresh);
    setValidationRun(fresh?.validation_run ?? null);
    return fresh;
  }

  function selectValidationRun(runId: string) {
    try {
      if (BodyFinderNative.selectValidationRun(runId)) refreshValidationState();
    } catch (cause: any) { setError(String(cause?.message ?? cause)); }
  }

  function toggleValidationRun() {
    if (validationActionLock.current) return;
    validationActionLock.current = true;
    try {
      if (validationRun?.active) {
        try { BodyFinderNative.updateValidationTruthJson(JSON.stringify(validationTruth)); } catch {}
        BodyFinderNative.endValidationRun();
        setValidationNotice(lang === 'es' ? 'Corrida finalizada y congelada.' : 'Run completed and frozen.');
      } else {
        const retained = Array.isArray(diagnostics?.completed_validation_runs_summary) ? diagnostics.completed_validation_runs_summary.length : 0;
        if (retained > 0) setValidationNotice(lang === 'es' ? 'La corrida completada anterior se conservará en el historial.' : 'The previous completed run will be preserved in history.');
        const result = BodyFinderNative.startValidationRun();
        if (typeof result === 'string' && result.startsWith('VALIDATION_ENVIRONMENT_INVALID:')) {
          const reason = result.split(':').slice(1).join(':');
          setError(lang === 'es' ? `Ambiente de validación inválido: ${reason}. Desactiva Battery Saver, mantén pantalla encendida y Body Finder en primer plano.` : `Invalid validation environment: ${reason}. Turn Battery Saver off, keep the screen on and Body Finder in foreground.`);
          return;
        }
      }
      refreshValidationState();
    } catch (cause: any) { setError(String(cause?.message ?? cause)); }
    finally { setTimeout(() => { validationActionLock.current = false; }, 600); }
  }

  async function share()'''
app = app[:old_toggle.start()] + new_toggle + app[old_toggle.end():]
app = app.replace('        BodyFinderNative.endValidationRun();\n        autoFinalizedValidationRun = true;', '        try { BodyFinderNative.updateValidationTruthJson(JSON.stringify(validationTruth)); } catch {}\n        BodyFinderNative.endValidationRun();\n        autoFinalizedValidationRun = true;')
app = app.replace('      validation_run: freshDiagnostics?.validation_run ?? null,', '      selected_validation_run_id: freshDiagnostics?.selected_validation_run_id ?? null,\n      validation_run: freshDiagnostics?.validation_run ?? null,\n      completed_validation_runs_summary: freshDiagnostics?.completed_validation_runs_summary ?? [],')
app = app.replace('      manual_geometry_override: false, human_scanning_enabled: HUMAN_SCANNING_ENABLED,', '      manual_geometry_override: false, human_scanning_enabled: HUMAN_SCANNING_ENABLED,\n      human_localization_validated: RELEASE.humanLocalizationValidated, rescue_use_validated: RELEASE.rescueUseValidated,')
app = app.replace("title: 'Body Finder experimental.11 validation integrity result'", "title: 'Body Finder experimental.11 validation integrity result'")
validation_card = '''          <View style={s.card}><Text style={s.h2}>Validation run</Text><Text style={s.text}>run: {validationRun?.run_id ?? '—'} · active: {String(Boolean(validationRun?.active))}</Text>
            <Text style={s.text}>elapsed: {validationRun?.elapsed_ms ?? 0} ms · frozen: {String(Boolean(validationRun?.snapshot_frozen))} · peer expiry Δ: {validationRun?.peer_expire_delta ?? 0} · rebind Δ: {validationRun?.address_rebind_delta ?? 0}</Text>
            <Text style={s.text}>peer: {formatPct(validationRun?.all_peer_uptime_percent)} · fresh metric: {formatPct(validationRun?.fresh_metric_range_uptime_percent)} · usable metric: {formatPct(validationRun?.usable_metric_range_uptime_percent)}</Text>
            <Text style={s.text}>holdover share: {formatPct(validationRun?.holdover_metric_uptime_percent)} · 2D: {formatPct(validationRun?.geometry_2d_uptime_percent)}</Text><Text style={s.text}>recovery attempts Δ: {validationRun?.recovery_attempt_delta ?? 0} · suppressed Δ: {validationRun?.restart_suppressed_delta ?? 0} · cohort stalls Δ: {validationRun?.cohort_stall_delta ?? 0}</Text></View>'''
validation_card_new = '''          <View style={s.card}><Text style={s.h2}>Validation run</Text><Text style={s.text}>run: {validationRun?.run_id ?? '—'} · active: {String(Boolean(validationRun?.active))}</Text>
            <Text style={s.text}>elapsed: {validationRun?.elapsed_ms ?? 0} ms · frozen: {String(Boolean(validationRun?.snapshot_frozen))} · schema: {validationRun?.snapshot_schema_version ?? RELEASE.snapshotSchemaVersion}</Text>
            <Text style={s.text}>ended: {validationRun?.ended_wall_ms ?? '—'} · retained: {diagnostics?.completed_validation_runs_summary?.length ?? 0}/5 · selected: {diagnostics?.selected_validation_run_id?.slice?.(-8) ?? '—'}</Text>
            <Text style={s.text}>peer expiry Δ: {validationRun?.peer_expire_delta ?? 0} · rebind Δ: {validationRun?.address_rebind_delta ?? 0}</Text>
            <Text style={s.text}>peer: {formatPct(validationRun?.all_peer_uptime_percent)} · fresh metric: {formatPct(validationRun?.fresh_metric_range_uptime_percent)} · usable metric: {formatPct(validationRun?.usable_metric_range_uptime_percent)}</Text>
            <Text style={s.text}>holdover share: {formatPct(validationRun?.holdover_metric_uptime_percent)} · 2D: {formatPct(validationRun?.geometry_2d_uptime_percent)}</Text><Text style={s.text}>recovery attempts Δ: {validationRun?.recovery_attempt_delta ?? 0} · suppressed Δ: {validationRun?.restart_suppressed_delta ?? 0} · cohort stalls Δ: {validationRun?.cohort_stall_delta ?? 0}</Text>
            {validationNotice && <Text style={s.muted}>{validationNotice}</Text>}
            {Array.isArray(diagnostics?.completed_validation_runs_summary) && diagnostics.completed_validation_runs_summary.map((run: any) => <Pressable key={run.run_id} style={s.btnAlt} onPress={() => selectValidationRun(run.run_id)}><Text style={s.btnText}>{run.run_id.slice(0, 8)} · {Math.round((run.elapsed_ms ?? 0) / 1000)}s · frozen {String(run.snapshot_frozen)}</Text></Pressable>)}
          </View>'''
if validation_card not in app: raise SystemExit('validation card exact block not found')
app = app.replace(validation_card, validation_card_new, 1)
write(app_path, app)

# ---------------------------------------------------------------------------
# Snapshot schema v2
# ---------------------------------------------------------------------------
schema = {
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "validation-run-snapshot-v2.schema.json",
  "title": "Body Finder CompletedValidationRun v2",
  "type": "object",
  "required": ["snapshot_schema_version","run_id","started_wall_ms","ended_wall_ms","elapsed_ms","snapshot_frozen","environment","validation_counters","acquisition_state_at_end","per_peer_at_end","system_ranging_at_end","events","geometry_at_end","fused_range_observations_at_end","graph_diagnostics_at_end"],
  "properties": {
    "snapshot_schema_version": {"const": 2},
    "run_id": {"type": "string", "minLength": 1},
    "started_wall_ms": {"type": "integer", "minimum": 0},
    "ended_wall_ms": {"type": "integer", "minimum": 0},
    "elapsed_ms": {"type": "integer", "minimum": 0},
    "snapshot_frozen": {"const": True},
    "environment": {"type": "object"},
    "validation_counters": {"type": "object"},
    "acquisition_state_at_end": {"type": "object"},
    "per_peer_at_end": {"type": "array"},
    "system_ranging_at_end": {"type": "object"},
    "events": {"type": "array", "items": {"type": "object", "required": ["seq","wall_ms","elapsed_ms","type"]}},
    "geometry_at_end": {},
    "locally_computed_geometry_at_end": {},
    "fused_range_observations_at_end": {"type": "array"},
    "graph_diagnostics_at_end": {},
    "reciprocal_fusion_at_end": {},
    "measurement_health_at_end": {}
  },
  "additionalProperties": True
}
write('protocol/schemas/validation-run-snapshot-v2.json', json.dumps(schema, indent=2) + '\n')
write('protocol/schemas/VALIDATION_SNAPSHOT_V1_TO_V2.md', '''# Validation snapshot v1 → v2\n\nv2 preserves the v1 run counters and adds bounded completed-run history, explicit selected-run export, recovery generations, canonical lifetime/run/recovery peer telemetry, and frozen geometry/fusion/graph truth at End. v1 readers may continue consuming legacy flat counters; v2 readers must prefer `per_peer_at_end` and the `*_at_end` geometry fields.\n''')

# ---------------------------------------------------------------------------
# Regression fixtures and tools
# ---------------------------------------------------------------------------
fixture_root = ROOT / 'validation/fixtures/dev11'
fixture_root.mkdir(parents=True, exist_ok=True)
valid_events = [
  {"seq":1,"wall_ms":1000,"elapsed_ms":0,"type":"BF_COHORT_STALLED","cohort_health":"BF_COHORT_STALLED","recovery_generation":None},
  {"seq":2,"wall_ms":1000,"elapsed_ms":0,"type":"RECOVERY_REQUESTED","cohort_health":"BF_COHORT_RECOVERING","recovery_generation":1},
  {"seq":3,"wall_ms":1000,"elapsed_ms":0,"type":"ACQUISITION_STRATEGY_CHANGED","cohort_health":"BF_COHORT_RECOVERING","recovery_generation":1},
  {"seq":4,"wall_ms":1200,"elapsed_ms":200,"type":"FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY","cohort_health":"BF_COHORT_RECOVERING","recovery_generation":1},
  {"seq":5,"wall_ms":1200,"elapsed_ms":200,"type":"RECOVERY_SUCCESS","cohort_health":"BF_COHORT_RECOVERING","recovery_generation":1},
]
write('validation/fixtures/dev11/timeline-valid.json', json.dumps({"events":valid_events}, indent=2)+'\n')
write('validation/fixtures/dev11/timeline-timestamp-inversion.json', json.dumps({"events":[valid_events[0], {**valid_events[1], "wall_ms":999}]}, indent=2)+'\n')
write('validation/fixtures/dev11/stalled-event-wrong-state.json', json.dumps({"events":[{**valid_events[0], "cohort_health":"BF_COHORT_HEALTHY"}]}, indent=2)+'\n')
write('validation/fixtures/dev11/duplicate-first-callback.json', json.dumps({"events":valid_events + [{**valid_events[3], "seq":6, "wall_ms":1300, "elapsed_ms":300}]}, indent=2)+'\n')
write('validation/fixtures/dev11/peer-lifetime-vs-run-scope.json', json.dumps({"peer":{"lifetime_gap_gt_5s_count":9,"run_gap_gt_5s_delta":0,"run_recovery_participation_count":1,"peer_recovery_count":1}}, indent=2)+'\n')
base_snapshot = {
  "snapshot_schema_version":2,"run_id":"run-long","started_wall_ms":1000,"ended_wall_ms":301000,"elapsed_ms":300000,"snapshot_frozen":True,
  "environment":{"valid":True},"validation_counters":{"peer_expire_delta":0},"acquisition_state_at_end":{},"per_peer_at_end":[],"system_ranging_at_end":{},
  "events":valid_events,"geometry_at_end":{"state":"GEOMETRY_2D","revision":7},"locally_computed_geometry_at_end":{"state":"GEOMETRY_2D","revision":7},
  "fused_range_observations_at_end":[],"graph_diagnostics_at_end":{"physical_confidence":"COARSE"},"reciprocal_fusion_at_end":{},"measurement_health_at_end":{"physical_confidence":"COARSE"}
}
write('validation/fixtures/dev11/post-end-live-counter-drift-v2.json', json.dumps({"completed":base_snapshot,"live_after_end":{"peer_expire_delta":3,"geometry_revision":9}}, indent=2)+'\n')
write('validation/fixtures/dev11/new-run-preserves-previous-completed.json', json.dumps({"history_limit":5,"completed":[base_snapshot,{**base_snapshot,"run_id":"run-short","elapsed_ms":2000,"ended_wall_ms":303000}]}, indent=2)+'\n')
write('validation/fixtures/dev11/geometry-at-end-drift.json', json.dumps({"completed":base_snapshot,"live_after_end":{"geometry_at_end":{"state":"GEOMETRY_2D","revision":9}}}, indent=2)+'\n')

common = '''#!/usr/bin/env python3\nimport json, pathlib, sys\nROOT=pathlib.Path(__file__).resolve().parents[2]\n'''
write('validation/android/check_recovery_timeline_contract.py', common + r'''
def errors(events):
    out=[]
    for a,b in zip(events,events[1:]):
        if b.get('seq',0)<=a.get('seq',0): out.append('seq')
        if b.get('wall_ms',0)<a.get('wall_ms',0): out.append('wall_ms')
        if b.get('elapsed_ms',0)<a.get('elapsed_ms',0): out.append('elapsed_ms')
    first={}
    stalls=[]
    requests=[]
    for e in events:
        if e.get('type')=='BF_COHORT_STALLED':
            stalls.append(e)
            if e.get('cohort_health')!='BF_COHORT_STALLED': out.append('stall_state')
        if e.get('type')=='RECOVERY_REQUESTED': requests.append(e)
        if e.get('type')=='FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY':
            g=e.get('recovery_generation'); first[g]=first.get(g,0)+1
    if any(v>1 for v in first.values()): out.append('duplicate_first')
    for req in requests:
        if not any(s.get('seq',0)<req.get('seq',0) and s.get('wall_ms',0)<=req.get('wall_ms',0) for s in stalls): out.append('request_before_stall')
    return out
valid=json.load(open(ROOT/'validation/fixtures/dev11/timeline-valid.json'))['events']
assert not errors(valid), errors(valid)
for name,expected in [('timeline-timestamp-inversion.json','wall_ms'),('stalled-event-wrong-state.json','stall_state'),('duplicate-first-callback.json','duplicate_first')]:
    assert expected in errors(json.load(open(ROOT/'validation/fixtures/dev11'/name))['events'])
src=(ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/ValidationEventLog.kt').read_text()
policy=(ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleAcquisitionPolicy.kt').read_text()
assert 'firstCallbackRecordedGeneration' in src and 'recovery_generation' in src
assert 'cohortHealth = next' in policy and 'activeRecoveryGeneration' in policy
print('PASS recovery timeline contract')
''')
write('validation/android/check_peer_telemetry_semantics.py', common + r'''
p=json.load(open(ROOT/'validation/fixtures/dev11/peer-lifetime-vs-run-scope.json'))['peer']
assert p['lifetime_gap_gt_5s_count']>p['run_gap_gt_5s_delta']
assert p['peer_recovery_count']==p['run_recovery_participation_count']
src=(ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleAcquisitionPolicy.kt').read_text()
assert 'peerRecoveryCount.incrementAndGet()' not in src
for k in ['lifetime_callback_count','run_filtered_callback_delta','run_unfiltered_callback_delta','run_recovery_participation_count','run_first_callback_after_recovery_count','last_recovery_generation_seen','last_recovery_callback_latency_ms']:
    assert k in src,k
print('PASS peer telemetry semantics')
''')
write('validation/android/check_geometry_snapshot_contract.py', common + r'''
src=(ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt').read_text()
for k in ['geometry_at_end','locally_computed_geometry_at_end','fused_range_observations_at_end','graph_diagnostics_at_end','reciprocal_fusion_at_end','measurement_health_at_end']:
    assert k in src,k
f=json.load(open(ROOT/'validation/fixtures/dev11/geometry-at-end-drift.json'))
assert f['completed']['geometry_at_end']['revision']==7
assert f['live_after_end']['geometry_at_end']['revision']==9
print('PASS geometry snapshot contract')
''')
write('validation/android/check_validation_snapshot_v2_contract.py', common + r'''
src=(ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt').read_text()
assert 'MAX_COMPLETED_VALIDATION_RUNS = 5' in src
assert 'completedRuns.addLast' in src and 'completedRuns.removeFirst' in src
assert 'snapshot_schema_version", 2' in src
assert 'selectedCompletedRunId' in src
assert 'validationTruthJson' in src
schema=json.load(open(ROOT/'protocol/schemas/validation-run-snapshot-v2.json'))
assert schema['properties']['snapshot_schema_version']['const']==2
fixture=json.load(open(ROOT/'validation/fixtures/dev11/new-run-preserves-previous-completed.json'))
assert fixture['completed'][0]['run_id']=='run-long' and fixture['completed'][1]['run_id']=='run-short'
print('PASS validation snapshot v2 contract')
''')
write('validation/android/check_version_truth_contract.py', common + r'''
app=(ROOT/'apps/mobile/App.tsx').read_text(); v=(ROOT/'apps/mobile/src/version.ts').read_text(); cfg=json.load(open(ROOT/'apps/mobile/app.json'))['expo']
assert "0.2.0-experimental.11" in v
assert 'reportVersion: 13' in v
assert cfg['android']['versionCode']==11
assert cfg['extra']['releaseIteration']=='experimental.11'
for stale in ['experimental.9','experimental.10']:
    assert stale not in app, stale
assert 'HUMAN_SCANNING_ENABLED' in app
print('PASS version truth contract')
''')
write('validation/android/check_dev11_frozen_truth_contract.py', common + r'''
import re
profile=json.load(open(ROOT/'calibration/ble-range-calibration-profiles.json'))
text=json.dumps(profile)
assert 'android-ble-lab-v1' in text and '-69.19' in text and '3.62' in text
cont=(ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleContinuityPolicy.kt').read_text()
pol=(ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleAcquisitionPolicy.kt').read_text()
for x in ['FRESH_MS = 5_000L','HOLDOVER_MAX_MS = 10_000L','SIGMA_AGING_M_PER_S = 0.15']: assert x in cont,x
for x in ['COHORT_STALL_THRESHOLD_MS = 5_000L','RECOVERY_UNFILTERED_WINDOW_MS = 10_000L','FILTERED_PROBE_WINDOW_MS = 15_000L','MIN_RESTART_COOLDOWN_MS = 30_000L','MAX_RECOVERY_ATTEMPTS_PER_5MIN = 3','SYSTEM_RANGING_BLE_YIELD_MS = 120_000L']: assert x in pol,x
core=(ROOT/'crates/body-finder-core/src/lib.rs').read_text(); assert 'pub const PROTOCOL_VERSION: u16 = 2;' in core
print('PASS dev11 frozen truth contract')
''')

write('validation/analysis/compare_validation_snapshots.py', r'''#!/usr/bin/env python3
import argparse,json

def select(payload, run_id=None):
    run=payload.get('validation_run')
    if run_id and run and run.get('run_id')==run_id: return run
    if run_id:
        for key in ('completed_validation_runs','validation_runs'):
            for item in payload.get(key,[]) or []:
                if item.get('run_id')==run_id: return item
    return run

p=argparse.ArgumentParser()
p.add_argument('export1'); p.add_argument('export2'); p.add_argument('--run-id')
a=p.parse_args()
x=select(json.load(open(a.export1,encoding='utf-8')),a.run_id); y=select(json.load(open(a.export2,encoding='utf-8')),a.run_id)
if not x or not y: raise SystemExit('FAIL: selected validation_run missing')
if not x.get('snapshot_frozen') or not y.get('snapshot_frozen'): raise SystemExit('FAIL: snapshot_frozen must be true')
if x!=y:
    dif=[k for k in sorted(set(x)|set(y)) if x.get(k)!=y.get(k)]
    raise SystemExit('FAIL: completed validation snapshot drift: '+', '.join(dif))
print('PASS: completed validation snapshot is immutable for run_id='+str(x.get('run_id')))
''')
write('validation/analysis/validate_recovery_timeline.py', r'''#!/usr/bin/env python3
import json,sys
p=json.load(open(sys.argv[1],encoding='utf-8')); events=(p.get('validation_run') or p).get('events',[])
last_seq=-1; last_wall=-1; last_elapsed=-1; first={}; stalls=[]
for e in events:
    assert e['seq']>last_seq,'non-monotonic seq'; assert e['wall_ms']>=last_wall,'non-monotonic wall_ms'; assert e.get('elapsed_ms',e.get('elapsed_from_run_start_ms',0))>=last_elapsed,'non-monotonic elapsed_ms'
    last_seq=e['seq']; last_wall=e['wall_ms']; last_elapsed=e.get('elapsed_ms',e.get('elapsed_from_run_start_ms',0))
    if e['type']=='BF_COHORT_STALLED': assert e.get('cohort_health')=='BF_COHORT_STALLED'; stalls.append(e)
    if e['type']=='RECOVERY_REQUESTED': assert any(s['seq']<e['seq'] for s in stalls),'recovery request before stall'
    if e['type']=='FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY':
        g=e.get('recovery_generation'); first[g]=first.get(g,0)+1; assert first[g]<=1,'duplicate first callback'
print('PASS timeline')
''')
write('validation/analysis/validate_peer_semantics.py', r'''#!/usr/bin/env python3
import json,sys
p=json.load(open(sys.argv[1],encoding='utf-8')); peers=(p.get('validation_run') or p).get('per_peer_at_end',(p.get('validation_run') or p).get('per_peer',[]))
for peer in peers:
    for key in ['run_callback_delta','run_valid_callback_delta','run_invalid_callback_delta','run_gap_gt_1s_delta','run_gap_gt_2s_delta','run_gap_gt_5s_delta','run_gap_gt_10s_delta','run_filtered_callback_delta','run_unfiltered_callback_delta','run_recovery_participation_count','run_first_callback_after_recovery_count']:
        if key in peer: assert peer[key]>=0,(key,peer[key])
    if (p.get('validation_run') or p).get('elapsed_ms',0)<5000: assert peer.get('run_gap_gt_5s_delta',0)<=1
print('PASS peer semantics')
''')
write('validation/analysis/validate_geometry_snapshot.py', r'''#!/usr/bin/env python3
import json,sys
p=json.load(open(sys.argv[1],encoding='utf-8')); r=p.get('validation_run') or p
assert r.get('snapshot_frozen') is True
for k in ['geometry_at_end','fused_range_observations_at_end','graph_diagnostics_at_end']: assert k in r,k
print('PASS geometry snapshot')
''')
write('validation/analysis/dev11_accuracy_report.py', r'''#!/usr/bin/env python3
import json,sys,math
# usage: script export1 export2 export3 ground-truth.json
exports=[json.load(open(x,encoding='utf-8')) for x in sys.argv[1:-1]]; gt=json.load(open(sys.argv[-1],encoding='utf-8'))
truth=gt.get('pairs',gt)
obs=[]
for p in exports:
    r=p.get('validation_run') or p
    for o in r.get('fused_range_observations_at_end',[]):
        a=o.get('from_node_id') or o.get('source_node_id'); b=o.get('to_node_id') or o.get('target_node_id'); d=o.get('distance_m')
        if a and b and isinstance(d,(int,float)): obs.append((a,b,float(d)))
errors=[]
for item in truth if isinstance(truth,list) else []:
    a=item.get('a'); b=item.get('b'); d=float(item['distance_m']); vals=[x[2] for x in obs if {x[0],x[1]}=={a,b}]
    if vals: errors.append(abs(sum(vals)/len(vals)-d))
out={'physical_confidence':'COARSE','directional_mae_m':sum(errors)/len(errors) if errors else None,'reciprocal_fused_mae_m':sum(errors)/len(errors) if errors else None,'maximum_absolute_error_m':max(errors) if errors else None,'uncertainty_coverage':None,'recalibration_gate':False}
print(json.dumps(out,indent=2))
''')

# ---------------------------------------------------------------------------
# Frozen truth and acceptance docs
# ---------------------------------------------------------------------------
write('DEV11_FROZEN_TRUTH.md', '''# dev-11 frozen truth\n\n- profile_id: `android-ble-lab-v1`\n- RSSI @ 1 m: `-69.19 dBm`\n- path-loss exponent: `3.62`\n- validated distance domain: `0.5–5.0 m`\n- minSamples: `3`\n- fresh: `5 s`\n- holdover/hard expiry: `10 s`\n- sigma aging: `0.15 m/s`\n- primary acquisition: `FILTERED_PRIMARY`\n- recovery acquisition: `UNFILTERED_RECOVERY`\n- cohort stall: `5 s`\n- recovery unfiltered: `10 s`\n- filtered probe: `15 s`\n- restart cooldown: `30 s`\n- max recoveries/5 min: `3`\n- API36 BLE yield: `120 s`\n- protocol: `2`\n- human_scanning_enabled: `false`\n- human_localization_validated: `false`\n- rescue_use_validated: `false`\n\nThese values are release gates and MUST NOT be changed by dev-11.\n''')
write('docs/ANDROID_DEV11_FINAL_ACCEPTANCE_RETEST.md', '''# Android dev-11 final acceptance retest\n\n## Install\nInstall **the same** `body-finder-ruview-universal.apk` from release `dev-11` on Pixel 10 Pro, Pixel 7 Pro and Lenovo TB-J606L. Confirm the UI says `0.2.0-experimental.11`.\n\n## Prepare\nOn all three: Bluetooth ON, Battery Saver OFF, screen ON, Body Finder foreground, same session. On Lenovo also Location ON. Arrange a non-collinear triangle with every pair between 0.5 m and 5.0 m. Measure the three distances with a tape and save them separately; do not enter them in the app.\n\n## Warm-up (30 s)\nOn each device verify: `nodes=3`, `BLE peers=2`, strategy `FILTERED_PRIMARY`, filter `MANUFACTURER_FILTERED`, hardware filter count > 0 and `environment_valid=true`.\n\n## Long run\n1. Tap **Start validation run** on all three.\n2. Do not move devices for **at least 5 minutes**.\n3. Tap **End validation run** on all three.\n4. Verify `snapshot_frozen=true`, schema `2`, elapsed >= 300000 ms.\n5. Export JSON from each device as `*_run_long_export1.json`.\n6. Keep apps active for >=3 more minutes.\n7. Export the same selected run again as `*_run_long_export2.json`.\n\n## History preservation\n1. Start a second short run, wait a few seconds, End.\n2. In **Validation run**, tap the previous long `run_id`.\n3. Export it as `*_run_long_after_short_run.json`.\n4. The long snapshot must be identical across all three exports.\n\n## Validate on Ubuntu/WSL/Windows\nExtract `body-finder-validation-tools.zip`, then for each device run:\n```bash\npython3 compare_validation_snapshots.py export1.json export2.json --run-id <LONG_RUN_ID>\npython3 compare_validation_snapshots.py export1.json after_short.json --run-id <LONG_RUN_ID>\npython3 validate_recovery_timeline.py export1.json\npython3 validate_peer_semantics.py export1.json\npython3 validate_geometry_snapshot.py export1.json\n```\nAll commands must print `PASS`.\n\n## Hard gates per device\n- `snapshot_frozen=true`\n- `elapsed_ms >= 300000`\n- `usable_metric_range_uptime_percent >= 90`\n- `geometry_2d_uptime_percent >= 90`\n- `peer_expire_delta = 0`\n- `recovery_attempt_delta <= 3`\n- `environment_valid=true`\n- timeline seq/wall/elapsed monotonic\n- `BF_COHORT_STALLED => cohort_health=BF_COHORT_STALLED`\n- max one first-valid callback per recovery generation\n- previous long run survives short run\n- geometry-at-End remains immutable\n\nAccuracy remains informative and `COARSE`; it is not a recalibration gate in dev-11. Human scanning and rescue-use validation remain disabled.\n''')

# ---------------------------------------------------------------------------
# CI experimental.11
# ---------------------------------------------------------------------------
ci10 = read('.github/workflows/ci-exp10.yml')
ci11 = ci10.replace('experimental.10','experimental.11').replace('exp10','exp11').replace('dev10','dev11')
ci11 = ci11.replace('branches: [main]', 'branches: [main, feat/dev11-post-validation-integrity]')
ci11 = ci11.replace('grep -q "0.2.0-experimental.11" apps/mobile/App.tsx', 'grep -q "0.2.0-experimental.11" apps/mobile/src/version.ts')
ci11 = ci11.replace('grep -q "HUMAN_SCANNING_ENABLED = false" apps/mobile/App.tsx', "grep -q 'humanScanningEnabled: false' apps/mobile/src/version.ts")
ci11 = ci11.replace('grep -q \'"versionCode": 10\' apps/mobile/app.json', 'grep -q \'"versionCode": 11\' apps/mobile/app.json')
ci11 = ci11.replace('python3 validation/android/check_validation_snapshot_contract.py', 'python3 validation/android/check_validation_snapshot_contract.py\n          python3 validation/android/check_validation_snapshot_v2_contract.py\n          python3 validation/android/check_recovery_timeline_contract.py\n          python3 validation/android/check_peer_telemetry_semantics.py\n          python3 validation/android/check_geometry_snapshot_contract.py\n          python3 validation/android/check_version_truth_contract.py\n          python3 validation/android/check_dev11_frozen_truth_contract.py')
ci11 = ci11.replace('python3 -m json.tool protocol/schemas/validation-run-snapshot-v1.json >/dev/null', 'python3 -m json.tool protocol/schemas/validation-run-snapshot-v2.json >/dev/null')
ci11 = ci11.replace('test -s docs/ANDROID_DEV10_VALIDATION_INTEGRITY_RETEST.md', 'test -s docs/ANDROID_DEV11_FINAL_ACCEPTANCE_RETEST.md')
ci11 = ci11.replace('test -s IMPLEMENTATION_PLAN_POST_DEV9_VALIDATION_INTEGRITY_AND_RECOVERY_PROVENANCE.md', 'test -s DEV11_FROZEN_TRUTH.md')
ci11 = ci11.replace('validation/analysis/compare_validation_snapshots.py validation/android/check_validation_snapshot_contract.py validation/android/check_acquisition_truth_contract.py', 'validation/analysis/compare_validation_snapshots.py validation/analysis/validate_recovery_timeline.py validation/analysis/validate_peer_semantics.py validation/analysis/validate_geometry_snapshot.py validation/android/check_validation_snapshot_v2_contract.py validation/android/check_recovery_timeline_contract.py validation/android/check_peer_telemetry_semantics.py validation/android/check_geometry_snapshot_contract.py validation/android/check_version_truth_contract.py')
write('.github/workflows/ci-exp11.yml', ci11)

# ---------------------------------------------------------------------------
# Release experimental.11 generated from verified dev10 pipeline then hardened.
# ---------------------------------------------------------------------------
rel = read('.github/workflows/release-exp10.yml')
rel = rel.replace('experimental.10','experimental.11').replace('experimental10','experimental11').replace('exp10','exp11').replace('DEV10','DEV11').replace('dev-10','dev-11')
rel = rel.replace('grep -q "0.2.0-experimental.11" apps/mobile/App.tsx', 'grep -q "0.2.0-experimental.11" apps/mobile/src/version.ts')
rel = rel.replace('grep -q "HUMAN_SCANNING_ENABLED = false" apps/mobile/App.tsx', "grep -q 'humanScanningEnabled: false' apps/mobile/src/version.ts")
rel = rel.replace('grep -q \'"versionCode": 10\' apps/mobile/app.json', 'grep -q \'"versionCode": 11\' apps/mobile/app.json')
rel = rel.replace('protocol/schemas/validation-run-snapshot-v1.json','protocol/schemas/validation-run-snapshot-v2.json')
rel = rel.replace('validation-run-snapshot-v1.schema.json','validation-run-snapshot-v2.schema.json')
rel = rel.replace('ANDROID_DEV10_VALIDATION_INTEGRITY_RETEST.md','ANDROID_DEV11_FINAL_ACCEPTANCE_RETEST.md')
rel = rel.replace('docs/ANDROID_DEV11_VALIDATION_INTEGRITY_RETEST.md','docs/ANDROID_DEV11_FINAL_ACCEPTANCE_RETEST.md')
rel = rel.replace('IMPLEMENTATION_PLAN_POST_DEV9_VALIDATION_INTEGRITY_AND_RECOVERY_PROVENANCE.md','IMPLEMENTATION_PLAN_POST_DEV10_DEV11_RELEASE.md')
rel = rel.replace('python3 validation/android/check_validation_snapshot_contract.py', 'python3 validation/android/check_validation_snapshot_contract.py\n          python3 validation/android/check_validation_snapshot_v2_contract.py\n          python3 validation/android/check_recovery_timeline_contract.py\n          python3 validation/android/check_peer_telemetry_semantics.py\n          python3 validation/android/check_geometry_snapshot_contract.py\n          python3 validation/android/check_version_truth_contract.py\n          python3 validation/android/check_dev11_frozen_truth_contract.py')
# Add dev11-specific fixture archives and ensure canonical plan/doc are copied.
anchor = '          mkdir -p dist/snapshot-fixtures && cp validation/fixtures/validation-snapshot/*.json dist/snapshot-fixtures/ && (cd dist/snapshot-fixtures && zip -r ../validation-snapshot-regression-fixtures.zip .) && rm -rf dist/snapshot-fixtures\n'
extra = anchor + '''          cp docs/ANDROID_DEV11_FINAL_ACCEPTANCE_RETEST.md dist/ANDROID_DEV11_FINAL_ACCEPTANCE_RETEST.md
          cp IMPLEMENTATION_PLAN_POST_DEV10_DEV11_RELEASE.md dist/IMPLEMENTATION_PLAN_POST_DEV10_DEV11_RELEASE.md
          cp protocol/schemas/validation-run-snapshot-v2.json dist/validation-run-snapshot-v2.schema.json
          mkdir -p dist/dev11-snapshot-fixtures && cp validation/fixtures/dev11/post-end-live-counter-drift-v2.json validation/fixtures/dev11/new-run-preserves-previous-completed.json dist/dev11-snapshot-fixtures/ && (cd dist/dev11-snapshot-fixtures && zip -r ../validation-snapshot-v2-regression-fixtures.zip .) && rm -rf dist/dev11-snapshot-fixtures
          mkdir -p dist/dev11-timeline-fixtures && cp validation/fixtures/dev11/timeline-*.json validation/fixtures/dev11/stalled-event-wrong-state.json validation/fixtures/dev11/duplicate-first-callback.json dist/dev11-timeline-fixtures/ && (cd dist/dev11-timeline-fixtures && zip -r ../recovery-timeline-regression-fixtures.zip .) && rm -rf dist/dev11-timeline-fixtures
          mkdir -p dist/dev11-peer-fixtures && cp validation/fixtures/dev11/peer-lifetime-vs-run-scope.json dist/dev11-peer-fixtures/ && (cd dist/dev11-peer-fixtures && zip -r ../peer-telemetry-regression-fixtures.zip .) && rm -rf dist/dev11-peer-fixtures
          mkdir -p dist/dev11-geometry-fixtures && cp validation/fixtures/dev11/geometry-at-end-drift.json dist/dev11-geometry-fixtures/ && (cd dist/dev11-geometry-fixtures && zip -r ../geometry-at-end-regression-fixtures.zip .) && rm -rf dist/dev11-geometry-fixtures
'''
if anchor not in rel: raise SystemExit('release snapshot anchor not found')
rel = rel.replace(anchor, extra, 1)
# Replace release manifest heredoc.
manifest = '''          cat > dist/release-manifest.json <<EOF
          {
            "schema_version": 11,
            "release": "dev-11",
            "commit": "${GITHUB_SHA}",
            "version": "0.2.0-experimental.11",
            "protocol_version": 2,
            "validation_snapshot_schema_version": 2,
            "validation_snapshot_immutable": true,
            "completed_validation_run_history": true,
            "completed_validation_run_history_limit": 5,
            "recovery_generation_enabled": true,
            "recovery_timeline_monotonic": true,
            "recovery_first_callback_exactly_once": true,
            "per_peer_run_scoped_telemetry": true,
            "geometry_snapshot_at_end": true,
            "automatic_geometry": true,
            "manual_node_coordinates_required": false,
            "ble_metric_profile": "android-ble-lab-v1",
            "ble_metric_profile_physical_confidence": "COARSE",
            "ble_metric_rssi_at_1m_dbm": -69.19,
            "ble_metric_path_loss_exponent": 3.62,
            "ble_metric_valid_distance_min_m": 0.5,
            "ble_metric_valid_distance_max_m": 5.0,
            "ble_metric_min_samples": 3,
            "ble_fresh_ms": 5000,
            "ble_holdover_max_ms": 10000,
            "ble_holdover_sigma_aging_m_per_s": 0.15,
            "ble_primary_strategy": "FILTERED_PRIMARY",
            "ble_recovery_strategy": "UNFILTERED_RECOVERY",
            "ble_cohort_stall_threshold_ms": 5000,
            "ble_recovery_unfiltered_window_ms": 10000,
            "ble_filtered_recovery_probe_ms": 15000,
            "ble_restart_cooldown_ms": 30000,
            "ble_max_recovery_attempts_per_5min": 3,
            "android_api36_ble_yield_ms": 120000,
            "human_scanning_enabled": false,
            "human_localization_validated": false,
            "rescue_use_validated": false
          }
          EOF'''
rel, count = re.subn(r'          cat > dist/release-manifest\.json <<EOF\n.*?          EOF', manifest, rel, count=1, flags=re.S)
if count != 1: raise SystemExit('manifest heredoc replacement failed')
# Harden mandatory artifact list and assertions.
rel = re.sub(r'          required=\([^\n]*\)', '''          required=(body-finder-ruview-universal.apk body-finder-ruview.aab body-finder-ruview-legacy-minsdk21.apk body-finder-node-linux-x86_64.tar.gz body-finder-node-linux-x86_64.deb body-finder-node-windows-x86_64.zip body-finder-ruview-ios-simulator.zip ANDROID_DEV11_FINAL_ACCEPTANCE_RETEST.md IMPLEMENTATION_PLAN_POST_DEV10_DEV11_RELEASE.md validation-run-snapshot-v2.schema.json validation-snapshot-v2-regression-fixtures.zip recovery-timeline-regression-fixtures.zip peer-telemetry-regression-fixtures.zip geometry-at-end-regression-fixtures.zip body-finder-validation-tools.zip release-manifest.json capability-matrix.json ble-range-calibration-profiles.json ble-range-calibration-schema.json protocol-version.txt model-manifest.json ruvview-upstream-lock.json SBOM.spdx.json)''', rel, count=1)
rel = rel.replace("assert m['validation_recovery_provenance'] is True", "assert m['completed_validation_run_history'] is True\n          assert m['recovery_generation_enabled'] is True\n          assert m['geometry_snapshot_at_end'] is True")
rel = rel.replace("grep -q 'validation-snapshot-regression-fixtures.zip' dist/SHA256SUMS", "grep -q 'validation-snapshot-v2-regression-fixtures.zip' dist/SHA256SUMS\n          grep -q 'recovery-timeline-regression-fixtures.zip' dist/SHA256SUMS")
rel = rel.replace('Start with ANDROID_DEV11_VALIDATION_INTEGRITY_RETEST.md.', 'Start with ANDROID_DEV11_FINAL_ACCEPTANCE_RETEST.md.')
write('.github/workflows/release-exp11.yml', rel)

# Release self-verifier.
verify = read('.github/workflows/verify-dev10-release.yml')
verify = verify.replace('dev-10','dev-11').replace('DEV10','DEV11').replace('dev10','dev11').replace('experimental.10','experimental.11')
verify = verify.replace('ANDROID_DEV11_VALIDATION_INTEGRITY_RETEST.md','ANDROID_DEV11_FINAL_ACCEPTANCE_RETEST.md')
verify = verify.replace('IMPLEMENTATION_PLAN_POST_DEV9_VALIDATION_INTEGRITY_AND_RECOVERY_PROVENANCE.md','IMPLEMENTATION_PLAN_POST_DEV10_DEV11_RELEASE.md')
verify = verify.replace('validation-run-snapshot-v1.schema.json','validation-run-snapshot-v2.schema.json')
verify = verify.replace('validation-snapshot-regression-fixtures.zip','validation-snapshot-v2-regression-fixtures.zip')
verify = verify.replace("assert manifest['validation_recovery_provenance'] is True", "assert manifest['completed_validation_run_history'] is True\n          assert manifest['recovery_generation_enabled'] is True\n          assert manifest['geometry_snapshot_at_end'] is True")
verify = verify.replace("'validation-run-snapshot-v2.schema.json','validation-snapshot-v2-regression-fixtures.zip',", "'validation-run-snapshot-v2.schema.json','validation-snapshot-v2-regression-fixtures.zip','recovery-timeline-regression-fixtures.zip','peer-telemetry-regression-fixtures.zip','geometry-at-end-regression-fixtures.zip',")
# Upload release-verification.json after verification, then commit it.
verify = verify.replace("          pathlib.Path('verification/dev11-release-verification.json').write_text(json.dumps(out,indent=2)+'\\n')", "          pathlib.Path('verification/dev11-release-verification.json').write_text(json.dumps(out,indent=2)+'\\n')")
verify = verify.replace('      - name: Persist verification report', '''      - name: Upload verification report to published release
        env:
          GH_TOKEN: ${{ github.token }}
        shell: bash
        run: gh release upload dev-11 verification/dev11-release-verification.json --clobber
      - name: Persist verification report''')
write('.github/workflows/verify-dev11-release.yml', verify)

# A compact release artifact model manifest note.
# Trigger files are created after merge, not here.

print('dev11 bootstrap completed')
