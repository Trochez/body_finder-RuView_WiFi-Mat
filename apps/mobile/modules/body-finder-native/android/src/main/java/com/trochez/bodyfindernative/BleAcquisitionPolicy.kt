package com.trochez.bodyfindernative

import android.bluetooth.le.BluetoothLeScanner
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanSettings
import android.os.Build
import org.json.JSONObject
import java.util.concurrent.ConcurrentLinkedDeque
import java.util.concurrent.atomic.AtomicLong
import kotlin.math.max

enum class BleAcquisitionStrategy {
  FILTERED_PRIMARY,
  UNFILTERED_RECOVERY,
  FILTERED_RECOVERY_PROBE,
  COOLDOWN,
  FAILED_SAFE,
}

enum class GlobalBleScannerHealth {
  GLOBAL_SCANNER_HEALTHY,
  GLOBAL_SCANNER_STALLED,
  GLOBAL_SCANNER_ERROR,
  GLOBAL_SCANNER_STARTING,
  GLOBAL_SCANNER_STOPPED,
}

enum class BodyFinderCohortHealth {
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

/**
 * Acquisition-only policy for experimental.15.
 *
 * Physical ranging truth is frozen: android-ble-lab-v1, minSamples=3,
 * freshness=5s, holdover=10s, sigma aging and solver rules are unchanged.
 */
internal object BleAcquisitionPolicy {
  const val PRIMARY_STRATEGY = "FILTERED_PRIMARY"
  const val RECOVERY_STRATEGY = "UNFILTERED_RECOVERY"
  const val REPORT_DELAY_MS = 0L
  const val MAX_INTERVAL_SAMPLES = 128
  const val GAP_1S_MS = 1_000L
  const val GAP_2S_MS = 2_000L
  const val GAP_5S_MS = 5_000L
  const val GAP_10S_MS = 10_000L

  const val GLOBAL_SCANNER_FRESH_MS = 2_000L
  const val COHORT_STALL_THRESHOLD_MS = 5_000L
  const val PEER_STARVATION_PERSIST_MS = 6_000L
  const val RECOVERY_UNFILTERED_WINDOW_MS = 10_000L
  const val FILTERED_PROBE_WINDOW_MS = 15_000L
  const val FILTERED_PROBE_EXIT_TARGET_MS = 14_500L
  const val MIN_RESTART_COOLDOWN_MS = 30_000L
  const val MAX_RECOVERY_ATTEMPTS_PER_5MIN = 3
  const val RECOVERY_ATTEMPT_WINDOW_MS = 300_000L
  const val RECOVERY_QUIET_MS = 250L

  const val SYSTEM_RANGING_BLE_YIELD_MS = 120_000L
  const val SYSTEM_RANGING_CLOSES_BEFORE_YIELD = 6L

  @Volatile private var strategy: BleAcquisitionStrategy = BleAcquisitionStrategy.FILTERED_PRIMARY
  @Volatile private var strategySinceWallMs: Long = 0L
  @Volatile private var lastStrategyReason: String = "STARTUP"
  @Volatile private var cohortHealth: BodyFinderCohortHealth = BodyFinderCohortHealth.BF_COHORT_UNAVAILABLE
  @Volatile private var transitionCount: Long = 0L
  @Volatile private var cohortStallCount: Long = 0L
  @Volatile private var cohortRecoveryCount: Long = 0L
  @Volatile private var cohortRecoveryFailureCount: Long = 0L
  @Volatile private var restartSuppressedCount: Long = 0L
  @Volatile private var recoveryAttemptCountTotal: Long = 0L
  @Volatile private var recoveryStartedWallMs: Long? = null
  @Volatile private var recoveryProbeStartedWallMs: Long? = null
  @Volatile private var recoveryProbeDeadlineWallMs: Long? = null
  @Volatile private var firstValidCallbackGeneration: Long? = null
  @Volatile private var firstValidCallbackPeerId: String? = null
  @Volatile private var firstValidCallbackWallMs: Long? = null
  @Volatile private var firstValidCallbackCountTotal: Long = 0L
  @Volatile private var lastRecoveryLatencyMs: Long? = null
  @Volatile private var lastRecoveryAttemptWallMs: Long = 0L
  @Volatile private var filteredAccumulatedMs: Long = 0L
  @Volatile private var unfilteredAccumulatedMs: Long = 0L
  private val recoveryAttemptWallMs = ConcurrentLinkedDeque<Long>()
  private val recoveryGenerationCounter = AtomicLong(0)
  @Volatile private var activeRecoveryGeneration: Long? = null
  @Volatile private var strategyRecoveryGeneration: Long? = null
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

  fun reset(now: Long = System.currentTimeMillis()) {
    strategy = BleAcquisitionStrategy.FILTERED_PRIMARY
    strategySinceWallMs = now
    lastStrategyReason = "STARTUP"
    cohortHealth = BodyFinderCohortHealth.BF_COHORT_UNAVAILABLE
    transitionCount = 0
    cohortStallCount = 0
    cohortRecoveryCount = 0
    cohortRecoveryFailureCount = 0
    restartSuppressedCount = 0
    recoveryAttemptCountTotal = 0
    recoveryStartedWallMs = null
    recoveryProbeStartedWallMs = null
    recoveryProbeDeadlineWallMs = null
    firstValidCallbackGeneration = null
    firstValidCallbackPeerId = null
    firstValidCallbackWallMs = null
    firstValidCallbackCountTotal = 0L
    lastRecoveryLatencyMs = null
    lastRecoveryAttemptWallMs = 0
    filteredAccumulatedMs = 0
    unfilteredAccumulatedMs = 0
    recoveryAttemptWallMs.clear()
    recoveryGenerationCounter.set(0)
    activeRecoveryGeneration = null
    strategyRecoveryGeneration = null
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
  }

  fun currentStrategy(): BleAcquisitionStrategy = strategy
  fun currentCohortHealth(): BodyFinderCohortHealth = cohortHealth
  fun strategySinceMs(): Long = strategySinceWallMs
  fun recoveryStartedMs(): Long? = recoveryStartedWallMs
  fun recoveryProbeStartedMs(): Long? = recoveryProbeStartedWallMs
  fun recoveryProbeDeadlineMs(): Long? = recoveryProbeDeadlineWallMs
  fun firstValidRecoveryGeneration(): Long? = firstValidCallbackGeneration
  fun firstValidRecoveryPeerId(): String? = firstValidCallbackPeerId
  fun firstValidRecoveryWallMs(): Long? = firstValidCallbackWallMs
  fun firstValidRecoveryCallbackCount(): Long = firstValidCallbackCountTotal
  fun transitionCount(): Long = transitionCount
  fun cohortStallCount(): Long = cohortStallCount
  fun cohortRecoveryCount(): Long = cohortRecoveryCount
  fun cohortRecoveryFailureCount(): Long = cohortRecoveryFailureCount
  fun restartSuppressedCount(): Long = restartSuppressedCount
  fun recoveryAttemptCount(): Long = recoveryAttemptCountTotal
  fun lastStrategyReason(): String = lastStrategyReason
  fun activeRecoveryGeneration(): Long? = activeRecoveryGeneration
  fun strategyRecoveryGeneration(): Long? = strategyRecoveryGeneration
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

  fun recoveryCallbackEligible(peerId: String?): Boolean {
    val generation = activeRecoveryGeneration ?: return false
    if (recoveryTerminalGeneration.get() == generation) return false
    return activeRecoveryTriggerKind != RecoveryTriggerKind.PEER_STARVATION ||
      (peerId != null && peerId == activeRecoveryTriggerPeerId)
  }
  @Synchronized fun recoveryAttemptsInWindow(now: Long): Int {
    while (true) {
      val first = recoveryAttemptWallMs.peekFirst() ?: break
      if (now - first <= RECOVERY_ATTEMPT_WINDOW_MS) break
      recoveryAttemptWallMs.pollFirst()
    }
    return recoveryAttemptWallMs.size
  }

  @Synchronized
  fun transition(next: BleAcquisitionStrategy, now: Long, reason: String) {
    if (strategy == next) return
    val previous = strategy
    accumulateCurrentMode(now)
    strategy = next
    strategySinceWallMs = now
    lastStrategyReason = reason
    strategyRecoveryGeneration = if (next == BleAcquisitionStrategy.UNFILTERED_RECOVERY || next == BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE) activeRecoveryGeneration else null
    if (next == BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE) {
      recoveryProbeStartedWallMs = now
      recoveryProbeDeadlineWallMs = now + FILTERED_PROBE_EXIT_TARGET_MS
    }
    transitionCount++
    ValidationEventLog.record(
      "ACQUISITION_STRATEGY_CHANGED", "$reason:${next.name}", now = now,
      fromStrategy = previous.name, toStrategy = next.name,
    )
    if (next == BleAcquisitionStrategy.FILTERED_PRIMARY || next == BleAcquisitionStrategy.FAILED_SAFE) {
      activeRecoveryGeneration = null
      strategyRecoveryGeneration = null
      activeRecoveryTriggerKind = null
      activeRecoveryTriggerPeerId = null
      recoveryStartedWallMs = null
      recoveryProbeStartedWallMs = null
      recoveryProbeDeadlineWallMs = null
      firstValidCallbackGeneration = null
      firstValidCallbackPeerId = null
      firstValidCallbackWallMs = null
    }
  }

  @Synchronized
  fun updateCohortHealth(next: BodyFinderCohortHealth, now: Long = System.currentTimeMillis()) {
    val previous = cohortHealth
    cohortHealth = next
    if (next == BodyFinderCohortHealth.BF_COHORT_STALLED && previous != BodyFinderCohortHealth.BF_COHORT_STALLED) {
      cohortStallCount++
      ValidationEventLog.record("BF_COHORT_STALLED", "GLOBAL_HEALTHY_BF_STALE", now = now)
    }
  }

  @Synchronized
  fun canStartRecovery(now: Long): Boolean {
    while (true) {
      val first = recoveryAttemptWallMs.peekFirst() ?: break
      if (now - first <= RECOVERY_ATTEMPT_WINDOW_MS) break
      recoveryAttemptWallMs.pollFirst()
    }
    if (lastRecoveryAttemptWallMs > 0 && now - lastRecoveryAttemptWallMs < MIN_RESTART_COOLDOWN_MS) {
      restartSuppressedCount++
      ValidationEventLog.record("RECOVERY_SUPPRESSED_COOLDOWN", "MIN_RESTART_COOLDOWN", now = now)
      return false
    }
    if (recoveryAttemptWallMs.size >= MAX_RECOVERY_ATTEMPTS_PER_5MIN) {
      restartSuppressedCount++
      ValidationEventLog.record("RECOVERY_SUPPRESSED_MAX_ATTEMPTS", "MAX_RECOVERY_ATTEMPTS_PER_5MIN", now = now)
      return false
    }
    return true
  }

  @Synchronized
  fun beginRecovery(
    now: Long,
    reason: String,
    triggerKind: RecoveryTriggerKind = RecoveryTriggerKind.FULL_COHORT_STALL,
    triggerPeerId: String? = null,
  ) {
    val active = activeRecoveryGeneration
    if (active != null && recoveryTerminalGeneration.get() != active) return
    if (active != null) {
      activeRecoveryGeneration = null
      strategyRecoveryGeneration = null
      activeRecoveryTriggerKind = null
      activeRecoveryTriggerPeerId = null
      recoveryStartedWallMs = null
    }
    recoveryAttemptCountTotal++
    recoveryAttemptWallMs.addLast(now)
    val generation = recoveryGenerationCounter.incrementAndGet()
    activeRecoveryGeneration = generation
    activeRecoveryTriggerKind = triggerKind
    activeRecoveryTriggerPeerId = triggerPeerId
    recoveryProbeStartedWallMs = null
    recoveryProbeDeadlineWallMs = null
    firstValidCallbackGeneration = null
    firstValidCallbackPeerId = null
    firstValidCallbackWallMs = null
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
  fun noteRecoveryFirstValidCallback(now: Long, peerId: String?): Boolean {
    val generation = activeRecoveryGeneration ?: return false
    if (strategy != BleAcquisitionStrategy.UNFILTERED_RECOVERY) return false
    if (!recoveryCallbackEligible(peerId)) return false
    if (firstValidCallbackGeneration == generation) return false
    firstValidCallbackGeneration = generation
    firstValidCallbackPeerId = peerId
    firstValidCallbackWallMs = now
    firstValidCallbackCountTotal++
    ValidationEventLog.record(
      "FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY", "BODY_FINDER_CALLBACK", now = now,
      peerId = peerId, triggerKind = activeRecoveryTriggerKind?.name,
      triggerPeerId = activeRecoveryTriggerPeerId,
    )
    return true
  }

  @Synchronized
  fun noteRecoverySuccess(now: Long, peerId: String? = null) {
    val generation = activeRecoveryGeneration ?: return
    if (recoveryTerminalGeneration.get() == generation) return
    if (firstValidCallbackGeneration != generation) return
    if (activeRecoveryTriggerKind == RecoveryTriggerKind.PEER_STARVATION &&
      (firstValidCallbackPeerId != activeRecoveryTriggerPeerId || peerId != activeRecoveryTriggerPeerId)) return
    recoveryTerminalGeneration.set(generation)
    recoverySuccessGeneration.set(generation)
    val start = recoveryStartedWallMs
    if (start != null) lastRecoveryLatencyMs = max(0L, now - start)
    cohortRecoveryCount++
    if (activeRecoveryTriggerKind == RecoveryTriggerKind.PEER_STARVATION) peerStarvationRecoverySuccessCount++
    ValidationEventLog.record(
      "RECOVERY_SUCCESS", "TARGET_FIRST_VALID_CONFIRMED", now = now,
      peerId = activeRecoveryTriggerPeerId ?: peerId, triggerKind = activeRecoveryTriggerKind?.name,
      triggerPeerId = activeRecoveryTriggerPeerId,
    )
    transition(BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE, now, "RECOVERY_SUCCESS")
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
      peerId = activeRecoveryTriggerPeerId, triggerKind = activeRecoveryTriggerKind?.name,
      triggerPeerId = activeRecoveryTriggerPeerId,
    )
    transition(BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE, now, "RECOVERY_FAILURE")
  }

  @Synchronized
  fun markFailedSafe(now: Long, reason: String) {
    transition(BleAcquisitionStrategy.FAILED_SAFE, now, reason)
  }

  /**
   * Establish a new validation-session boundary without weakening the frozen
   * rolling recovery budget or cooldown. Only filtered terminal safety states
   * may be normalized; an active recovery/probe generation must finish first.
   */
  @Synchronized
  fun prepareValidationRunBoundary(now: Long = System.currentTimeMillis()): Boolean {
    return when (strategy) {
      BleAcquisitionStrategy.FILTERED_PRIMARY -> true
      BleAcquisitionStrategy.FAILED_SAFE,
      BleAcquisitionStrategy.COOLDOWN -> {
        if (activeRecoveryGeneration != null || strategyRecoveryGeneration != null) return false
        transition(BleAcquisitionStrategy.FILTERED_PRIMARY, now, "VALIDATION_RUN_BOUNDARY")
        ValidationEventLog.record(
          "VALIDATION_SESSION_BOUNDARY_RESET", "FILTERED_TERMINAL_STATE_TO_PRIMARY", now = now,
          fromStrategy = null, toStrategy = BleAcquisitionStrategy.FILTERED_PRIMARY.name,
          authorizationReason = "PRESERVE_RECOVERY_BUDGET_AND_COOLDOWN",
        )
        true
      }
      BleAcquisitionStrategy.UNFILTERED_RECOVERY,
      BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE -> false
    }
  }

  private fun isFiltered(s: BleAcquisitionStrategy): Boolean =
    s == BleAcquisitionStrategy.FILTERED_PRIMARY || s == BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE || s == BleAcquisitionStrategy.COOLDOWN

  private fun accumulateCurrentMode(now: Long) {
    val elapsed = max(0L, now - strategySinceWallMs)
    if (strategy == BleAcquisitionStrategy.UNFILTERED_RECOVERY) unfilteredAccumulatedMs += elapsed
    else if (isFiltered(strategy)) filteredAccumulatedMs += elapsed
  }

  fun filteredTotalMs(now: Long): Long = filteredAccumulatedMs + if (isFiltered(strategy)) max(0L, now - strategySinceWallMs) else 0L
  fun unfilteredTotalMs(now: Long): Long = unfilteredAccumulatedMs + if (strategy == BleAcquisitionStrategy.UNFILTERED_RECOVERY) max(0L, now - strategySinceWallMs) else 0L

  fun scanSettings(): ScanSettings {
    val builder = ScanSettings.Builder()
      .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
      .setReportDelay(REPORT_DELAY_MS)
      .setCallbackType(ScanSettings.CALLBACK_TYPE_ALL_MATCHES)
    if (Build.VERSION.SDK_INT >= 23) {
      builder.setMatchMode(ScanSettings.MATCH_MODE_AGGRESSIVE)
        .setNumOfMatches(ScanSettings.MATCH_NUM_MAX_ADVERTISEMENT)
    }
    return builder.build()
  }

  fun manufacturerFilter(manufacturerId: Int): ScanFilter {
    val prefix = byteArrayOf(0x42, 0x46)
    val mask = byteArrayOf(0xff.toByte(), 0xff.toByte())
    return ScanFilter.Builder().setManufacturerData(manufacturerId, prefix, mask).build()
  }

  fun startFilteredScan(scanner: BluetoothLeScanner, callback: ScanCallback, manufacturerId: Int) {
    scanner.startScan(listOf(manufacturerFilter(manufacturerId)), scanSettings(), callback)
  }

  fun startUnfilteredRecoveryScan(scanner: BluetoothLeScanner, callback: ScanCallback) {
    scanner.startScan(null, scanSettings(), callback)
  }

  fun matchModeLabel(): String = if (Build.VERSION.SDK_INT >= 23) "AGGRESSIVE" else "PLATFORM_DEFAULT"
  fun numMatchesLabel(): String = if (Build.VERSION.SDK_INT >= 23) "MAX_ADVERTISEMENT" else "PLATFORM_DEFAULT"

  fun diagnostics(now: Long): JSONObject = JSONObject()
    .put("primary_strategy", PRIMARY_STRATEGY)
    .put("recovery_strategy", RECOVERY_STRATEGY)
    .put("acquisition_strategy", strategy.name)
    .put("strategy_since_wall_ms", strategySinceWallMs)
    .put("strategy_age_ms", max(0L, now - strategySinceWallMs))
    .put("strategy_transition_count", transitionCount)
    .put("last_strategy_reason", lastStrategyReason)
    .put("body_finder_cohort_health", cohortHealth.name)
    .put("cohort_stall_count", cohortStallCount)
    .put("cohort_recovery_count", cohortRecoveryCount)
    .put("cohort_recovery_failure_count", cohortRecoveryFailureCount)
    .put("cohort_recovery_last_latency_ms", lastRecoveryLatencyMs ?: JSONObject.NULL)
    .put("recovery_started_wall_ms", recoveryStartedWallMs ?: JSONObject.NULL)
    .put("recovery_probe_started_wall_ms", recoveryProbeStartedWallMs ?: JSONObject.NULL)
    .put("recovery_probe_deadline_wall_ms", recoveryProbeDeadlineWallMs ?: JSONObject.NULL)
    .put("probe_elapsed_ms", recoveryProbeStartedWallMs?.let { max(0L, now - it) } ?: JSONObject.NULL)
    .put("probe_remaining_ms", recoveryProbeDeadlineWallMs?.let { max(0L, it - now) } ?: JSONObject.NULL)
    .put("first_valid_callback_generation", firstValidCallbackGeneration ?: JSONObject.NULL)
    .put("first_valid_callback_peer_id", firstValidCallbackPeerId ?: JSONObject.NULL)
    .put("first_valid_callback_wall_ms", firstValidCallbackWallMs ?: JSONObject.NULL)
    .put("restart_suppressed_by_cooldown_count", restartSuppressedCount)
    .put("recovery_attempt_count", recoveryAttemptCountTotal)
    .put("recovery_attempts_in_current_5min_window", recoveryAttemptsInWindow(now))
    .put("filtered_mode_total_ms", filteredTotalMs(now))
    .put("unfiltered_recovery_total_ms", unfilteredTotalMs(now))
    .put("cohort_stall_threshold_ms", COHORT_STALL_THRESHOLD_MS)
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
    .put("active_recovery_generation", activeRecoveryGeneration ?: JSONObject.NULL)
    .put("strategy_recovery_generation", strategyRecoveryGeneration ?: JSONObject.NULL)
    .put("active_recovery_trigger_kind", activeRecoveryTriggerKind?.name ?: JSONObject.NULL)
    .put("active_recovery_trigger_peer_id", activeRecoveryTriggerPeerId ?: JSONObject.NULL)
    .put("recovery_unfiltered_window_ms", RECOVERY_UNFILTERED_WINDOW_MS)
    .put("filtered_probe_window_ms", FILTERED_PROBE_WINDOW_MS)
    .put("filtered_probe_exit_target_ms", FILTERED_PROBE_EXIT_TARGET_MS)
    .put("restart_cooldown_ms", MIN_RESTART_COOLDOWN_MS)
    .put("max_recovery_attempts_per_5min", MAX_RECOVERY_ATTEMPTS_PER_5MIN)

  fun health(callbackCount: Long, currentGapMs: Long?, valid5s: Int, valid8s: Int): String = when {
    callbackCount <= 0L -> "NO_BODY_FINDER_CALLBACK"
    currentGapMs == null -> "ACQUISITION_STARTING"
    currentGapMs >= GAP_10S_MS -> "ACQUISITION_GAP_10S"
    currentGapMs >= GAP_5S_MS -> "ACQUISITION_GAP_5S"
    currentGapMs >= GAP_2S_MS -> "ACQUISITION_GAP_2S"
    valid5s >= 3 -> "ACQUISITION_HEALTHY"
    valid8s >= 3 -> "ACQUISITION_SPARSE"
    else -> "ACQUISITION_SPARSE"
  }
}

internal data class BleAcquisitionCounterSnapshot(
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
)

internal class BleAcquisitionStats {
  private val firstCallbackWallMs = AtomicLong(0)
  private val lastCallbackWallMs = AtomicLong(0)
  private val callbackCount = AtomicLong(0)
  private val validCallbackCount = AtomicLong(0)
  private val invalidCallbackCount = AtomicLong(0)
  private val filteredCallbackCount = AtomicLong(0)
  private val unfilteredCallbackCount = AtomicLong(0)
  private val intervalCount = AtomicLong(0)
  private val intervalSumMs = AtomicLong(0)
  private val maxIntervalMs = AtomicLong(0)
  private val gapGt1sCount = AtomicLong(0)
  private val gapGt2sCount = AtomicLong(0)
  private val gapGt5sCount = AtomicLong(0)
  private val gapGt10sCount = AtomicLong(0)
  private val recentIntervalsMs = ConcurrentLinkedDeque<Long>()
  private val recoveryParticipationCount = AtomicLong(0)
  private val firstCallbackAfterRecoveryCount = AtomicLong(0)
  private val lastRecoveryGenerationSeen = AtomicLong(0)
  private val lastFirstValidRecoveryGeneration = AtomicLong(0)
  private val lastRecoveryCallbackLatencyMs = AtomicLong(0)
  @Volatile private var lastCallbackStrategy: String? = null
  @Volatile private var lastValidCallbackStrategy: String? = null

  private fun markGeneration(slot: AtomicLong, generation: Long): Boolean {
    while (true) {
      val previous = slot.get()
      if (previous == generation) return false
      if (slot.compareAndSet(previous, generation)) return true
    }
  }

  fun record(now: Long, validRssi: Boolean, strategy: BleAcquisitionStrategy = BleAcquisitionPolicy.currentStrategy()) {
    firstCallbackWallMs.compareAndSet(0L, now)
    val previous = lastCallbackWallMs.getAndSet(now)
    callbackCount.incrementAndGet()
    lastCallbackStrategy = strategy.name
    if (strategy == BleAcquisitionStrategy.UNFILTERED_RECOVERY) unfilteredCallbackCount.incrementAndGet() else filteredCallbackCount.incrementAndGet()
    if (validRssi) {
      validCallbackCount.incrementAndGet()
      lastValidCallbackStrategy = strategy.name
      if (strategy == BleAcquisitionStrategy.UNFILTERED_RECOVERY) {
        val generation = BleAcquisitionPolicy.activeRecoveryGeneration()
        if (generation != null) {
          if (markGeneration(lastRecoveryGenerationSeen, generation)) recoveryParticipationCount.incrementAndGet()
          val started = BleAcquisitionPolicy.recoveryStartedMs()
          if (started != null) lastRecoveryCallbackLatencyMs.set(max(0L, now - started))
        }
      }
    } else invalidCallbackCount.incrementAndGet()
    if (previous <= 0L) return
    val interval = max(0L, now - previous)
    intervalCount.incrementAndGet()
    intervalSumMs.addAndGet(interval)
    while (true) {
      val old = maxIntervalMs.get()
      if (interval <= old || maxIntervalMs.compareAndSet(old, interval)) break
    }
    if (interval > BleAcquisitionPolicy.GAP_1S_MS) gapGt1sCount.incrementAndGet()
    if (interval > BleAcquisitionPolicy.GAP_2S_MS) gapGt2sCount.incrementAndGet()
    if (interval > BleAcquisitionPolicy.GAP_5S_MS) gapGt5sCount.incrementAndGet()
    if (interval > BleAcquisitionPolicy.GAP_10S_MS) gapGt10sCount.incrementAndGet()
    recentIntervalsMs.addLast(interval)
    while (recentIntervalsMs.size > BleAcquisitionPolicy.MAX_INTERVAL_SAMPLES) recentIntervalsMs.pollFirst()
  }

  fun noteFirstValidRecovery(generation: Long, now: Long) {
    if (markGeneration(lastFirstValidRecoveryGeneration, generation)) {
      firstCallbackAfterRecoveryCount.incrementAndGet()
      val started = BleAcquisitionPolicy.recoveryStartedMs()
      if (started != null) lastRecoveryCallbackLatencyMs.set(max(0L, now - started))
    }
  }

  fun snapshot(): BleAcquisitionCounterSnapshot = BleAcquisitionCounterSnapshot(
    callbackCount.get(), validCallbackCount.get(), invalidCallbackCount.get(),
    gapGt1sCount.get(), gapGt2sCount.get(), gapGt5sCount.get(), gapGt10sCount.get(),
    filteredCallbackCount.get(), unfilteredCallbackCount.get(),
    recoveryParticipationCount.get(), firstCallbackAfterRecoveryCount.get(),
  )

  private fun percentile(values: List<Long>, p: Double): Any {
    if (values.isEmpty()) return JSONObject.NULL
    val sorted = values.sorted()
    val index = ((sorted.size - 1) * p).toInt().coerceIn(0, sorted.lastIndex)
    return sorted[index]
  }

  fun diagnostics(now: Long, valid5s: Int, valid8s: Int, baseline: BleAcquisitionCounterSnapshot? = null): JSONObject {
    val first = firstCallbackWallMs.get().takeIf { it > 0L }
    val last = lastCallbackWallMs.get().takeIf { it > 0L }
    val intervals = recentIntervalsMs.toList()
    val totalIntervals = intervalCount.get()
    val mean: Any = if (totalIntervals <= 0L) JSONObject.NULL else intervalSumMs.get().toDouble() / totalIntervals.toDouble()
    val currentGap: Long? = last?.let { max(0L, now - it) }
    val durationMs = if (first == null) 0L else max(1L, now - first)
    val rateHz: Any = if (first == null) JSONObject.NULL else callbackCount.get().toDouble() * 1000.0 / durationMs.toDouble()
    val validRateHz: Any = if (first == null) JSONObject.NULL else validCallbackCount.get().toDouble() * 1000.0 / durationMs.toDouble()
    val snap = snapshot()
    fun delta(current: Long, previous: Long?): Long = (current - (previous ?: 0L)).coerceAtLeast(0L)
    return JSONObject()
      .put("acquisition_health", BleAcquisitionPolicy.health(snap.callbackCount, currentGap, valid5s, valid8s))
      .put("first_callback_wall_ms", first ?: JSONObject.NULL)
      .put("last_callback_wall_ms", last ?: JSONObject.NULL)
      .put("current_gap_ms", currentGap ?: JSONObject.NULL)
      .put("callback_count", snap.callbackCount)
      .put("lifetime_callback_count", snap.callbackCount)
      .put("valid_rssi_callback_count", snap.validCallbackCount)
      .put("invalid_rssi_callback_count", snap.invalidCallbackCount)
      .put("callback_rate_hz", rateHz)
      .put("valid_callback_rate_hz", validRateHz)
      .put("mean_interarrival_ms", mean)
      .put("max_interarrival_ms", if (totalIntervals > 0L) maxIntervalMs.get() else JSONObject.NULL)
      .put("p50_interarrival_ms", percentile(intervals, 0.50))
      .put("p95_interarrival_ms", percentile(intervals, 0.95))
      .put("gap_gt_1s_count", snap.gapGt1sCount)
      .put("gap_gt_2s_count", snap.gapGt2sCount)
      .put("gap_gt_5s_count", snap.gapGt5sCount)
      .put("gap_gt_10s_count", snap.gapGt10sCount)
      .put("lifetime_gap_gt_1s_count", snap.gapGt1sCount)
      .put("lifetime_gap_gt_2s_count", snap.gapGt2sCount)
      .put("lifetime_gap_gt_5s_count", snap.gapGt5sCount)
      .put("lifetime_gap_gt_10s_count", snap.gapGt10sCount)
      .put("last_callback_strategy", lastCallbackStrategy ?: JSONObject.NULL)
      .put("last_valid_callback_strategy", lastValidCallbackStrategy ?: JSONObject.NULL)
      .put("callbacks_filtered_mode", snap.filteredCallbackCount)
      .put("callbacks_unfiltered_mode", snap.unfilteredCallbackCount)
      .put("run_callback_delta", delta(snap.callbackCount, baseline?.callbackCount))
      .put("run_valid_callback_delta", delta(snap.validCallbackCount, baseline?.validCallbackCount))
      .put("run_invalid_callback_delta", delta(snap.invalidCallbackCount, baseline?.invalidCallbackCount))
      .put("run_gap_gt_1s_delta", delta(snap.gapGt1sCount, baseline?.gapGt1sCount))
      .put("run_gap_gt_2s_delta", delta(snap.gapGt2sCount, baseline?.gapGt2sCount))
      .put("run_gap_gt_5s_delta", delta(snap.gapGt5sCount, baseline?.gapGt5sCount))
      .put("run_gap_gt_10s_delta", delta(snap.gapGt10sCount, baseline?.gapGt10sCount))
      .put("run_filtered_callback_delta", delta(snap.filteredCallbackCount, baseline?.filteredCallbackCount))
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
      .put("peer_recovery_latency_ms", lastRecoveryCallbackLatencyMs.get().takeIf { it > 0 } ?: JSONObject.NULL)
  }
}
