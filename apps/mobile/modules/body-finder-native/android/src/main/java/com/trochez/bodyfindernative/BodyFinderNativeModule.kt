package com.trochez.bodyfindernative

import android.Manifest
import android.bluetooth.BluetoothManager
import android.bluetooth.le.AdvertiseCallback
import android.bluetooth.le.AdvertiseData
import android.bluetooth.le.AdvertiseSettings
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.ClipData
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.location.LocationManager
import android.net.wifi.WifiManager
import android.os.Build
import android.os.PowerManager
import android.os.SystemClock
import android.view.WindowManager
import androidx.core.content.FileProvider
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.DatagramPacket
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.MulticastSocket
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.ConcurrentLinkedDeque
import java.util.concurrent.atomic.AtomicLong
import kotlin.concurrent.thread
import kotlin.math.max

private const val PORT = 47777
private const val GROUP = "239.255.77.77"
private const val PROTOCOL = 2
private const val MANUFACTURER_ID = 0x05F1
private const val RANGE_PERMISSION = "android.permission.RANGING"
private const val PEER_STALE_MS = 5_000L
private const val PEER_EXPIRY_MS = 10_000L
private const val RANGE_FRESHNESS_MS = 5_000L
private const val WINDOW_RETENTION_MS = 8_000L
private const val MIN_SAMPLES_FOR_RANGE = 3
private const val MAX_RSSI_SAMPLES = 21
private const val MAX_INVALID_RSSI_EVENTS = 21
private const val SCAN_STALL_RESTART_MS = 12_000L
private const val SCAN_RESTART_COOLDOWN_MS = 10_000L
private const val MAX_REBIND_EVENTS = 64

private data class RssiSample(val rssi: Int, val txPower: Int, val ms: Long)
private data class InvalidRssiEvent(val rssi: Int, val ms: Long)
private data class RebindEvent(
  val identity: String,
  val previousFingerprint: String,
  val newFingerprint: String,
  val wallMs: Long,
  val reason: String,
)

private data class CompletedValidationRun(val runId: String, val snapshotJson: String)
private data class PeerStarvationCounterSnapshot(
  val starvationCount: Long,
  val recoveryParticipationCount: Long,
  val firstValidCallbackCount: Long,
  val recoverySuccessCount: Long,
  val recoveryFailureCount: Long,
)

private object ValidationRuntime {
  const val MAX_COMPLETED_VALIDATION_RUNS = 5
  @Volatile var runId: String? = null
  @Volatile var scenario: String = "UNSPECIFIED"
  @Volatile var startedWallMs: Long? = null
  @Volatile var endedWallMs: Long? = null
  @Volatile var appVisibility: String = "UNKNOWN"
  @Volatile var geometryState: String = "UNKNOWN"
  @Volatile private var lastObserveWallMs: Long? = null
  @Volatile private var peerFullUptimeMs: Long = 0
  @Volatile private var rangeEvidenceUptimeMs: Long = 0
  @Volatile private var freshMetricRangeUptimeMs: Long = 0
  @Volatile private var usableMetricRangeUptimeMs: Long = 0
  @Volatile private var singleRemotePeerMetricUptimeMs: Long = 0
  @Volatile private var allExpectedPeerMetricUptimeMs: Long = 0
  @Volatile private var expectedPeerCountAtStart: Int = 0
  @Volatile private var expectedPeerIdsAtStart: List<String> = emptyList()
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
  @Volatile private var preflightAtStartJson: String = "{}"
  @Volatile private var authorizedStrategyTransitionCount: Long = 0
  @Volatile private var authorizedRecoveryIntervalCount: Long = 0
  @Volatile private var unauthorizedStrategyViolationCount: Long = 0
  @Volatile private var lastEnvironmentStrategy: String? = null
  @Volatile private var lastAuthorizedRecoveryGeneration: Long? = null
  @Volatile private var baselineStrategyTransitions: Long = 0
  @Volatile private var baselineCohortStalls: Long = 0
  @Volatile private var baselineCohortRecoveries: Long = 0
  @Volatile private var baselineCohortRecoveryFailures: Long = 0
  @Volatile private var baselineRecoveryAttempts: Long = 0
  @Volatile private var baselineFirstValidCallbacks: Long = 0
  @Volatile private var baselineRestartSuppressed: Long = 0
  @Volatile private var baselineRangingYield: Long = 0
  @Volatile private var baselineRangingReal: Long = 0
  @Volatile private var baselineRangingClose: Long = 0
  @Volatile private var baselineEventSeq: Long = 0
  @Volatile private var baselinePeerStarvation: Long = 0
  @Volatile private var baselinePeerStarvationRecoveryRequest: Long = 0
  @Volatile private var baselinePeerStarvationRecoverySuccess: Long = 0
  @Volatile private var baselinePeerStarvationRecoveryFailure: Long = 0
  @Volatile private var validationTruthJson: String = "{}"
  @Volatile private var authoritativeTruthLedgerJson: String = "{}"
  @Volatile private var campaignRunToken: String? = null
  @Volatile private var distributedStartCommitted: Boolean = false
  @Volatile private var distributedFreezeCommitted: Boolean = false
  @Volatile private var distributedContextJson: String = "{}"
  @Volatile private var distributedFreezeCommitJson: String = "{}"
  @Volatile private var scenarioGeneration: Long = 0
  @Volatile private var scenarioStartedWallMs: Long = 0
  @Volatile private var selectedCompletedRunId: String? = null
  private val completedRuns = java.util.ArrayDeque<CompletedValidationRun>()

  @Synchronized
  fun start(now: Long, peerExpire: Long, rebind: Long, scanRestart: Long, tx: Long, rx: Long, preflightJson: String, scenarioId: String): String {
    if (runId != null && endedWallMs == null) return runId!!
    require(scenarioId.isNotBlank() && scenarioId != "UNSPECIFIED") { "SCENARIO_UNSPECIFIED" }
    val id = UUID.randomUUID().toString()
    scenario = scenarioId
    scenarioGeneration += 1
    scenarioStartedWallMs = now
    runId = id
    startedWallMs = now
    endedWallMs = null
    lastObserveWallMs = now
    peerFullUptimeMs = 0
    rangeEvidenceUptimeMs = 0
    freshMetricRangeUptimeMs = 0
    usableMetricRangeUptimeMs = 0
    singleRemotePeerMetricUptimeMs = 0
    allExpectedPeerMetricUptimeMs = 0
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
    EnvironmentViolationTracker.reset()
    val frozenPreflight = try { JSONObject(preflightJson) } catch (_: Throwable) { JSONObject() }
    preflightAtStartJson = frozenPreflight.toString()
    val frozenPeerIds = frozenPreflight.optJSONArray("expected_ble_peer_ids") ?: JSONArray()
    expectedPeerIdsAtStart = (0 until frozenPeerIds.length()).mapNotNull { frozenPeerIds.optString(it).takeIf(String::isNotBlank) }.distinct().sorted()
    expectedPeerCountAtStart = max(frozenPreflight.optInt("expected_ble_peer_count", expectedPeerIdsAtStart.size), expectedPeerIdsAtStart.size)
    FabricEventTimeline.start(id, now, expectedPeerIdsAtStart)
    HumanEvidenceTimeline.start(id, now)
    authorizedStrategyTransitionCount = 0
    authorizedRecoveryIntervalCount = 0
    unauthorizedStrategyViolationCount = 0
    lastEnvironmentStrategy = BleAcquisitionStrategy.FILTERED_PRIMARY.name
    lastAuthorizedRecoveryGeneration = null
    baselineStrategyTransitions = BleAcquisitionPolicy.transitionCount()
    baselineCohortStalls = BleAcquisitionPolicy.cohortStallCount()
    baselineCohortRecoveries = BleAcquisitionPolicy.cohortRecoveryCount()
    baselineCohortRecoveryFailures = BleAcquisitionPolicy.cohortRecoveryFailureCount()
    baselineRecoveryAttempts = BleAcquisitionPolicy.recoveryAttemptCount()
    baselineFirstValidCallbacks = BleAcquisitionPolicy.firstValidRecoveryCallbackCount()
    baselineRestartSuppressed = BleAcquisitionPolicy.restartSuppressedCount()
    val r = if (Build.VERSION.SDK_INT >= 36) SystemRangingApi36.counterSnapshot() else SystemRangingCounterSnapshot(0, 0, 0)
    baselineRangingYield = r.yieldTransitions
    baselineRangingReal = r.realDistanceResults
    baselineRangingClose = r.closeFailures
    baselineEventSeq = ValidationEventLog.currentSeq()
    baselinePeerStarvation = BleAcquisitionPolicy.peerStarvationCount()
    baselinePeerStarvationRecoveryRequest = BleAcquisitionPolicy.peerStarvationRecoveryRequestCount()
    baselinePeerStarvationRecoverySuccess = BleAcquisitionPolicy.peerStarvationRecoverySuccessCount()
    baselinePeerStarvationRecoveryFailure = BleAcquisitionPolicy.peerStarvationRecoveryFailureCount()
    validationTruthJson = "{}"
    authoritativeTruthLedgerJson = "{}"
    campaignRunToken = null
    distributedStartCommitted = false
    distributedFreezeCommitted = false
    distributedContextJson = "{}"
    distributedFreezeCommitJson = "{}"
    ValidationEventLog.record("VALIDATION_RUN_STARTED", id, now = now)
    return id
  }

  @Synchronized
  fun pinDistributedStart(contextJson:String):Boolean{val activeRunId=runId?:return false;if(endedWallMs!=null)return false;val o=try{JSONObject(contextJson)}catch(_:Throwable){return false};val token=o.optString("campaign_run_token");if(token.isBlank()||o.optBoolean("committed")!=true)return false;campaignRunToken=token;distributedStartCommitted=true;distributedContextJson=o.toString();ValidationEventLog.record("DISTRIBUTED_RUN_START_COMMITTED",activeRunId,now=System.currentTimeMillis());return true}
  @Synchronized fun requiresDistributedCommit():Boolean=distributedStartCommitted
  @Synchronized fun freezeCommitted():Boolean=distributedFreezeCommitted
  @Synchronized fun commitDistributedFreeze(commitJson:String):Boolean{val activeRunId=runId?:return false;if(endedWallMs!=null||!distributedStartCommitted)return false;val o=try{JSONObject(commitJson)}catch(_:Throwable){return false};if(o.optBoolean("committed")!=true||o.optString("campaign_run_token")!=campaignRunToken||o.optInt("ready_count")!=3||!o.optBoolean("ready_parity"))return false;distributedFreezeCommitted=true;distributedFreezeCommitJson=o.toString();ValidationEventLog.record("DISTRIBUTED_RUN_FREEZE_COMMITTED",activeRunId,now=System.currentTimeMillis());return true}

  @Synchronized
  fun frozenExpectedPeerCount(): Int = expectedPeerCountAtStart

  @Synchronized
  fun frozenExpectedPeerIds(): List<String> = expectedPeerIdsAtStart.toList()

  @Synchronized
  fun observe(now: Long, activePeerCount: Int, evidenceReadyPeerCount: Int, freshMetricReadyPeerCount: Int, usableMetricReadyPeerCount: Int) {
    if (runId == null || endedWallMs != null) return
    val previous = lastObserveWallMs ?: now
    val dt = (now - previous).coerceIn(0L, 5_000L)
    val expected = expectedPeerCountAtStart.coerceAtLeast(2)
    if (activePeerCount >= expected) peerFullUptimeMs += dt
    if (evidenceReadyPeerCount >= expected) rangeEvidenceUptimeMs += dt
    if (freshMetricReadyPeerCount >= expected) freshMetricRangeUptimeMs += dt
    if (usableMetricReadyPeerCount >= expected) usableMetricRangeUptimeMs += dt
    if (usableMetricReadyPeerCount >= 1) singleRemotePeerMetricUptimeMs += dt
    if (usableMetricReadyPeerCount >= expected) allExpectedPeerMetricUptimeMs += dt
    if (usableMetricReadyPeerCount >= expected && freshMetricReadyPeerCount < expected) holdoverMetricUptimeMs += dt
    if (geometryState == "GEOMETRY_2D") geometry2dUptimeMs += dt
    lastObserveWallMs = now
  }

  @Synchronized
  fun updateTruth(json: String) {
    if (runId == null || endedWallMs != null) return
    val incoming = try { JSONObject(json) } catch (_: Throwable) { JSONObject() }
    incoming.put("scenario", scenario).put("scenario_generation", scenarioGeneration).put("scenario_started_wall_ms", scenarioStartedWallMs)
    validationTruthJson = incoming.toString()
    val p = incoming.optJSONObject("authoritative_presence")
    val admissible = p != null && p.optBoolean("authoritative", false) && p.optString("canonical_digest").isNotBlank() && p.optString("decision_id").isNotBlank() && p.optJSONObject("canonical_replay_input") != null && p.optInt("contributing_nodes",0) >= 3 && p.optInt("contributing_links",0) >= 6 && p.optInt("physical_baselines",0) >= 3
    if (admissible) authoritativeTruthLedgerJson = incoming.toString()
  }

  @Synchronized
  fun end(now: Long, peerExpire: Long, rebind: Long, scanRestart: Long, tx: Long, rx: Long, acquisitionState: JSONObject, perPeer: JSONArray, systemRanging: JSONObject) {
    val id = runId ?: return
    if (endedWallMs != null) return
    endedWallMs = now
    lastObserveWallMs = now
    ValidationEventLog.record("VALIDATION_RUN_ENDED", id, now = now)
    HumanEvidenceTimeline.end(now)
    val base = liveDiagnostics(now, peerExpire, rebind, scanRestart, tx, rx)
    val timeline = ValidationEventLog.snapshotSince(baselineEventSeq, startedWallMs ?: now)
    val events = timeline.optJSONArray("events") ?: JSONArray()
    var stallsDuringYield = 0
    for (i in 0 until events.length()) {
      val e = events.optJSONObject(i) ?: continue
      if (e.optString("type") == "BF_COHORT_STALLED" && e.optBoolean("ranging_yield_active")) stallsDuringYield++
    }
    val liveTruth = try { JSONObject(validationTruthJson) } catch (_: Throwable) { JSONObject() }
    val ledgerTruth = try { JSONObject(authoritativeTruthLedgerJson) } catch (_: Throwable) { JSONObject() }
    val ledgerPresence = ledgerTruth.optJSONObject("authoritative_presence")
    val truth = if (ledgerPresence != null && ledgerPresence.optBoolean("authoritative", false) && ledgerPresence.optString("canonical_digest").isNotBlank()) ledgerTruth else liveTruth
    val environmentIntervals = EnvironmentViolationTracker.snapshot(now)
    environmentViolationCount = environmentIntervals.optLong("violation_count")
    firstEnvironmentViolationWallMs = environmentIntervals.optLong("first_violation_wall_ms").takeIf { it > 0L }
    environmentViolationTypes = (0 until environmentIntervals.optJSONArray("violation_types").length()).map { environmentIntervals.optJSONArray("violation_types").optString(it) }.joinToString(",")
    val environment = JSONObject()
      .put("valid", environmentViolationCount == 0L)
      .put("violation_count", environmentViolationCount)
      .put("first_violation_wall_ms", firstEnvironmentViolationWallMs ?: JSONObject.NULL)
      .put("violation_types", if (environmentViolationTypes.isBlank()) JSONArray() else JSONArray(environmentViolationTypes.split(',')))
      .put("authorized_strategy_transition_count", authorizedStrategyTransitionCount)
      .put("authorized_recovery_interval_count", authorizedRecoveryIntervalCount)
      .put("unauthorized_strategy_violation_count", unauthorizedStrategyViolationCount)
      .put("environment_violation_events", environmentIntervals.optJSONArray("events"))
      .put("total_background_ms", environmentIntervals.optLong("total_background_ms"))
      .put("max_background_interval_ms", environmentIntervals.optLong("max_background_interval_ms"))
      .put("foreground_transition_count", environmentIntervals.optLong("foreground_transition_count"))
      .put("unresolved_violation_count", environmentIntervals.optLong("unresolved_violation_count"))
    val requestWalls = mutableListOf<Long>()
    val generations = mutableMapOf<Long, MutableList<JSONObject>>()
    for (i in 0 until events.length()) {
      val e = events.optJSONObject(i) ?: continue
      val g = e.optLong("recovery_generation", Long.MIN_VALUE)
      if (g != Long.MIN_VALUE) generations.getOrPut(g) { mutableListOf() }.add(e)
      if (e.optString("type") == "RECOVERY_REQUESTED") requestWalls += e.optLong("wall_ms")
    }
    var rollingMax = 0
    requestWalls.sorted().forEach { start -> rollingMax = max(rollingMax, requestWalls.count { it >= start && it <= start + BleAcquisitionPolicy.RECOVERY_ATTEMPT_WINDOW_MS }) }
    var maxUnfiltered = 0L; var unfilteredTargetMisses = 0; var unfilteredBreaches = 0
    var maxProbe = 0L; var probeTargetMisses = 0; var probeBreaches = 0
    generations.values.forEach { group ->
      val request = group.firstOrNull { it.optString("type") == "RECOVERY_REQUESTED" }
      val terminal = group.firstOrNull { it.optString("type") == "RECOVERY_SUCCESS" || it.optString("type") == "RECOVERY_FAILURE" }
      if (request != null && terminal != null) {
        val d = max(0L, terminal.optLong("wall_ms") - request.optLong("wall_ms")); maxUnfiltered = max(maxUnfiltered,d)
        if (d > BleAcquisitionPolicy.RECOVERY_UNFILTERED_ACTION_TARGET_MS) unfilteredTargetMisses++
        if (d > BleAcquisitionPolicy.RECOVERY_UNFILTERED_WINDOW_MS) unfilteredBreaches++
      }
      val ps = group.firstOrNull { it.optString("type") == "ACQUISITION_STRATEGY_CHANGED" && it.optString("to_strategy") == "FILTERED_RECOVERY_PROBE" }
      val pe = group.firstOrNull { it.optString("type") == "ACQUISITION_STRATEGY_CHANGED" && it.optString("from_strategy") == "FILTERED_RECOVERY_PROBE" }
      if (ps != null) {
        val d = max(0L, (pe?.optLong("wall_ms") ?: now) - ps.optLong("wall_ms")); maxProbe=max(maxProbe,d)
        if (d > BleAcquisitionPolicy.FILTERED_PROBE_EXIT_TARGET_MS) probeTargetMisses++
        if (d > BleAcquisitionPolicy.FILTERED_PROBE_WINDOW_MS) probeBreaches++
      }
    }
    acquisitionState
      .put("recovery_unfiltered_hard_limit_ms", BleAcquisitionPolicy.RECOVERY_UNFILTERED_WINDOW_MS)
      .put("recovery_unfiltered_action_target_ms", BleAcquisitionPolicy.RECOVERY_UNFILTERED_ACTION_TARGET_MS)
      .put("filtered_probe_exit_target_ms", BleAcquisitionPolicy.FILTERED_PROBE_EXIT_TARGET_MS)
      .put("filtered_probe_hard_limit_ms", BleAcquisitionPolicy.FILTERED_PROBE_WINDOW_MS)
      .put("filtered_probe_action_target_ms", BleAcquisitionPolicy.FILTERED_PROBE_ACTION_TARGET_MS)
      .put("recovery_budget_window_ms", BleAcquisitionPolicy.RECOVERY_ATTEMPT_WINDOW_MS)
      .put("recovery_budget_limit", BleAcquisitionPolicy.MAX_RECOVERY_ATTEMPTS_PER_5MIN)
      .put("recovery_attempt_delta_total", base.optLong("recovery_attempt_delta"))
      .put("recovery_attempts_in_current_5min_window_at_end", requestWalls.count { now - it <= BleAcquisitionPolicy.RECOVERY_ATTEMPT_WINDOW_MS })
      .put("recovery_attempts_max_in_any_rolling_5min_window", rollingMax)
    val timingSummary = JSONObject()
      .put("generation_count", generations.size)
      .put("max_unfiltered_duration_ms", maxUnfiltered)
      .put("unfiltered_action_target_miss_count", unfilteredTargetMisses)
      .put("unfiltered_hard_limit_breach_count", unfilteredBreaches)
      .put("max_filtered_probe_duration_ms", maxProbe)
      .put("filtered_probe_target_miss_count", probeTargetMisses)
      .put("filtered_probe_hard_limit_breach_count", probeBreaches)

    val counters = JSONObject()
      .put("peer_expire_delta", base.optLong("peer_expire_delta"))
      .put("address_rebind_delta", base.optLong("address_rebind_delta"))
      .put("scan_restart_delta", base.optLong("scan_restart_delta"))
      .put("tx_packets_delta", base.optLong("tx_packets_delta"))
      .put("rx_packets_delta", base.optLong("rx_packets_delta"))
      .put("recovery_attempt_delta", base.optLong("recovery_attempt_delta"))
      .put("recovery_first_valid_callback_delta", base.optLong("recovery_first_valid_callback_delta"))
      .put("cohort_stall_delta", base.optLong("cohort_stall_delta"))
      .put("peer_starvation_delta", base.optLong("peer_starvation_delta"))
      .put("peer_starvation_recovery_request_delta", base.optLong("peer_starvation_recovery_request_delta"))
      .put("peer_starvation_recovery_success_delta", base.optLong("peer_starvation_recovery_success_delta"))
      .put("peer_starvation_recovery_failure_delta", base.optLong("peer_starvation_recovery_failure_delta"))
    base
      .put("local_snapshot_frozen", true).put("distributed_start_committed", distributedStartCommitted).put("distributed_freeze_committed", distributedFreezeCommitted).put("campaign_run_token", campaignRunToken ?: JSONObject.NULL).put("distributed_start_context", try { JSONObject(distributedContextJson) } catch (_: Throwable) { JSONObject() }).put("distributed_freeze_commit", try { JSONObject(distributedFreezeCommitJson) } catch (_: Throwable) { JSONObject() }).put("snapshot_frozen", !distributedStartCommitted || distributedFreezeCommitted)
      .put("snapshot_schema_version", 16)
      .put("expected_peer_count_at_start", expectedPeerCountAtStart)
      .put("expected_peer_ids_at_start", JSONArray(expectedPeerIdsAtStart))
      .put("preflight_at_start", try { JSONObject(preflightAtStartJson) } catch (_: Throwable) { JSONObject() })
      .put("fabric_event_timeline", FabricEventTimeline.snapshot(now))
      .put("human_evidence", HumanEvidenceTimeline.snapshot(now))
      .put("expected_peer_loss_intervals", FabricEventTimeline.lossIntervals(now))
      .put("environment", environment)
      .put("environment_violation_events", environmentIntervals.optJSONArray("events"))
      .put("validation_counters", counters)
      .put("acquisition_state_at_end", acquisitionState)
      .put("recovery_timing_summary", timingSummary)
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
      .put("validation_truth", truth)
    val frozenPresence = truth.optJSONObject("authoritative_presence")
    val invalidReasons = JSONArray()
    if (frozenPresence == null || !frozenPresence.optBoolean("authoritative", false)) invalidReasons.put("NO_FROZEN_AUTHORITATIVE_DECISION")
    if (frozenPresence == null || frozenPresence.optString("canonical_digest").isBlank()) invalidReasons.put("MISSING_CANONICAL_DIGEST")
    if (frozenPresence == null || frozenPresence.optString("decision_id").isBlank()) invalidReasons.put("MISSING_DECISION_ID")
    if (frozenPresence == null || frozenPresence.optJSONObject("canonical_replay_input") == null) invalidReasons.put("MISSING_CANONICAL_REPLAY")
    if (frozenPresence != null && (frozenPresence.optInt("contributing_nodes",0) < 3 || frozenPresence.optInt("contributing_links",0) < 6 || frozenPresence.optInt("physical_baselines",0) < 3)) invalidReasons.put("INCOMPLETE_3_6_3_TOPOLOGY")
    val evidenceValid = invalidReasons.length() == 0
    val scenarioMaterial="$id|$scenario|$scenarioGeneration|${startedWallMs ?: 0L}|$now"
    val scenarioDigest="sha256:"+MessageDigest.getInstance("SHA-256").digest(scenarioMaterial.toByteArray(Charsets.UTF_8)).joinToString(""){"%02x".format(it)}
    base.put("scenario",scenario).put("scenario_generation",scenarioGeneration).put("scenario_started_wall_ms",scenarioStartedWallMs).put("scenario_consistency_digest",scenarioDigest)
    base.put("evidence_export_valid", evidenceValid)
      .put("evidence_invalid_reasons", invalidReasons)
      .put("atomic_snapshot_gate_pass", evidenceValid)
      .put("snapshot_consistency_digest", frozenPresence?.optString("canonical_digest")?.takeIf { it.isNotBlank() } ?: JSONObject.NULL)
      .put("authoritative_decision_ledger_used", ledgerPresence != null)
    val snapshotBytes = base.toString().toByteArray(Charsets.UTF_8)
    val snapshotHash = MessageDigest.getInstance("SHA-256").digest(snapshotBytes).joinToString("") { "%02x".format(it) }
    base.put("snapshot_identity_sha256", snapshotHash).put("json_self_contained", true).put("screenshots_required", false)
    val frozen = CompletedValidationRun(id, base.toString())
    completedRuns.addLast(frozen)
    while (completedRuns.size > MAX_COMPLETED_VALIDATION_RUNS) completedRuns.removeFirst()
    selectedCompletedRunId = id
  }

  @Synchronized
  fun updateGeometry(state: String) { geometryState = state }

  @Synchronized
  fun recordEnvironmentEvaluation(
    now: Long,
    issues: List<String>,
    decision: StrategyEnvironmentDecision,
    strategy: BleAcquisitionStrategy,
    recoveryGeneration: Long?,
    triggerKind: RecoveryTriggerKind?,
    triggerPeerId: String?,
    ctx: Context,
  ) {
    if (runId == null || endedWallMs != null) return
    val previous = lastEnvironmentStrategy
    if (previous != strategy.name && decision.authorized) {
      authorizedStrategyTransitionCount++
      ValidationEventLog.record(
        "ENVIRONMENT_STRATEGY_TRANSITION_AUTHORIZED", decision.authorizationReason, now = now,
        peerId = triggerPeerId, triggerKind = triggerKind?.name,
        fromStrategy = previous, toStrategy = strategy.name, authorizationReason = decision.authorizationReason,
      )
    }
    lastEnvironmentStrategy = strategy.name
    if (decision.authorized && (strategy == BleAcquisitionStrategy.UNFILTERED_RECOVERY || strategy == BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE) && recoveryGeneration != null && lastAuthorizedRecoveryGeneration != recoveryGeneration) {
      authorizedRecoveryIntervalCount++
      lastAuthorizedRecoveryGeneration = recoveryGeneration
    }
    if (!decision.valid) unauthorizedStrategyViolationCount++
    val power = ctx.getSystemService(Context.POWER_SERVICE) as? PowerManager
    EnvironmentViolationTracker.observe(now, issues, EnvironmentObservation(
      appVisibility, power?.isInteractive == true, power?.isPowerSaveMode == true,
      FieldServiceState.state == "RUNNING", FabricRuntime.bleScanning, strategy.name, recoveryGeneration, "ENVIRONMENT_EVALUATION"
    ))
    environmentViolationCount = EnvironmentViolationTracker.count()
    firstEnvironmentViolationWallMs = EnvironmentViolationTracker.firstWallMs()
    environmentViolationTypes = EnvironmentViolationTracker.types().joinToString(",")
  }

  private fun liveDiagnostics(now: Long, peerExpire: Long, rebind: Long, scanRestart: Long, tx: Long, rx: Long): JSONObject {
    val start = startedWallMs
    val effectiveEnd = endedWallMs ?: now
    val elapsed = if (start == null) 0L else max(0L, effectiveEnd - start)
    fun pct(value: Long): Any = if (elapsed <= 0) JSONObject.NULL else (100.0 * value / elapsed.toDouble())
    return JSONObject()
      .put("active", runId != null && endedWallMs == null)
      .put("run_id", runId ?: JSONObject.NULL)
      .put("scenario", scenario)
      .put("scenario_generation", scenarioGeneration)
      .put("scenario_started_wall_ms", scenarioStartedWallMs)
      .put("started_wall_ms", start ?: JSONObject.NULL)
      .put("ended_wall_ms", endedWallMs ?: JSONObject.NULL)
      .put("snapshot_wall_ms", effectiveEnd)
      .put("snapshot_elapsed_ms", elapsed)
      .put("elapsed_ms", elapsed)
      .put("acceptance_minimum_ms", 330_000L)
      .put("acceptance_duration_eligible", elapsed >= 330_000L)
      .put("short_diagnostic_run", elapsed in 1 until 330_000L)
      .put("keep_awake_policy", "FLAG_KEEP_SCREEN_ON_DURING_ACTIVE_VALIDATION")
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
      .put("single_remote_peer_metric_uptime_percent", pct(singleRemotePeerMetricUptimeMs))
      .put("all_expected_peer_metric_uptime_percent", pct(allExpectedPeerMetricUptimeMs))
      .put("holdover_metric_uptime_percent", pct(holdoverMetricUptimeMs))
      .put("metric_range_uptime_percent", pct(usableMetricRangeUptimeMs))
      .put("geometry_2d_uptime_percent", pct(geometry2dUptimeMs))
      .put("environment_valid", environmentViolationCount == 0L)
      .put("environment_violation_count", environmentViolationCount)
      .put("first_environment_violation_wall_ms", firstEnvironmentViolationWallMs ?: JSONObject.NULL)
      .put("environment_violation_types", if (environmentViolationTypes.isBlank()) JSONArray() else JSONArray(environmentViolationTypes.split(',')))
      .put("preflight_at_start", try { JSONObject(preflightAtStartJson) } catch (_: Throwable) { JSONObject() })
      .put("fabric_event_timeline", FabricEventTimeline.snapshot(now))
      .put("expected_peer_loss_intervals", FabricEventTimeline.lossIntervals(now))
      .put("authorized_strategy_transition_count", authorizedStrategyTransitionCount)
      .put("authorized_recovery_interval_count", authorizedRecoveryIntervalCount)
      .put("unauthorized_strategy_violation_count", unauthorizedStrategyViolationCount)
      .put("strategy_transition_delta", (BleAcquisitionPolicy.transitionCount() - baselineStrategyTransitions).coerceAtLeast(0))
      .put("cohort_stall_delta", (BleAcquisitionPolicy.cohortStallCount() - baselineCohortStalls).coerceAtLeast(0))
      .put("cohort_recovery_delta", (BleAcquisitionPolicy.cohortRecoveryCount() - baselineCohortRecoveries).coerceAtLeast(0))
      .put("cohort_recovery_failure_delta", (BleAcquisitionPolicy.cohortRecoveryFailureCount() - baselineCohortRecoveryFailures).coerceAtLeast(0))
      .put("recovery_attempt_delta", (BleAcquisitionPolicy.recoveryAttemptCount() - baselineRecoveryAttempts).coerceAtLeast(0))
      .put("recovery_first_valid_callback_delta", (BleAcquisitionPolicy.firstValidRecoveryCallbackCount() - baselineFirstValidCallbacks).coerceAtLeast(0))
      .put("restart_suppressed_delta", (BleAcquisitionPolicy.restartSuppressedCount() - baselineRestartSuppressed).coerceAtLeast(0))
      .put("peer_starvation_delta", (BleAcquisitionPolicy.peerStarvationCount() - baselinePeerStarvation).coerceAtLeast(0))
      .put("peer_starvation_recovery_request_delta", (BleAcquisitionPolicy.peerStarvationRecoveryRequestCount() - baselinePeerStarvationRecoveryRequest).coerceAtLeast(0))
      .put("peer_starvation_recovery_success_delta", (BleAcquisitionPolicy.peerStarvationRecoverySuccessCount() - baselinePeerStarvationRecoverySuccess).coerceAtLeast(0))
      .put("peer_starvation_recovery_failure_delta", (BleAcquisitionPolicy.peerStarvationRecoveryFailureCount() - baselinePeerStarvationRecoveryFailure).coerceAtLeast(0))
      .put("ranging_yield_transition_delta", ((if (Build.VERSION.SDK_INT >= 36) SystemRangingApi36.counterSnapshot().yieldTransitions else 0) - baselineRangingYield).coerceAtLeast(0))
      .put("ranging_real_result_delta", ((if (Build.VERSION.SDK_INT >= 36) SystemRangingApi36.counterSnapshot().realDistanceResults else 0) - baselineRangingReal).coerceAtLeast(0))
      .put("ranging_close_failure_delta", ((if (Build.VERSION.SDK_INT >= 36) SystemRangingApi36.counterSnapshot().closeFailures else 0) - baselineRangingClose).coerceAtLeast(0))
      .put("local_snapshot_frozen", false).put("distributed_start_committed", distributedStartCommitted).put("distributed_freeze_committed", distributedFreezeCommitted).put("campaign_run_token", campaignRunToken ?: JSONObject.NULL).put("snapshot_frozen", false)
      .put("snapshot_schema_version", 16)
      .put("expected_peer_count_at_start", expectedPeerCountAtStart)
      .put("expected_peer_ids_at_start", JSONArray(expectedPeerIdsAtStart))
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
        .put("scenario", j.optString("scenario"))
        .put("scenario_generation", j.optLong("scenario_generation"))
        .put("scenario_consistency_digest", j.opt("scenario_consistency_digest"))
        .put("started_wall_ms", j.opt("started_wall_ms"))
        .put("ended_wall_ms", j.opt("ended_wall_ms"))
        .put("elapsed_ms", j.optLong("elapsed_ms"))
        .put("snapshot_frozen", j.optBoolean("snapshot_frozen"))
        .put("snapshot_schema_version", j.optInt("snapshot_schema_version"))
        .put("acceptance_minimum_ms", j.optLong("acceptance_minimum_ms"))
        .put("acceptance_duration_eligible", j.optBoolean("acceptance_duration_eligible"))
        .put("short_diagnostic_run", j.optBoolean("short_diagnostic_run"))
        .put("environment_valid", j.optBoolean("environment_valid"))
        .put("usable_metric_range_uptime_percent", j.opt("usable_metric_range_uptime_percent"))
        .put("geometry_2d_uptime_percent", j.opt("geometry_2d_uptime_percent"))
        .put("peer_expire_delta", j.optLong("peer_expire_delta"))
        .put("recovery_attempt_delta", j.optLong("recovery_attempt_delta")))
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


private object WireTransportV10 {
  private const val RANGE_FRAME_SCHEMA = "RangeFrameV9"
  const val MAX_DATAGRAM_BYTES = 1200
  const val RANGE_FRAME_TARGET_BYTES = 1050
  const val CONTROL_FRAME_TARGET_BYTES = 900
  const val COMPACT_CONTROL_PAYLOAD_TARGET_BYTES = 600
  private const val GEOMETRY_PUBLICATION_LEASE_MS = 6_000L
  private const val CHUNK_BYTES = 512
  private const val ASSEMBLY_TIMEOUT_MS = 15_000L
  private const val NACK_INTERVAL_MS = 1_000L
  private const val FULL_RETRY_MS = 3_000L
  private const val MAX_RETRY_BACKOFF_MS = 12_000L
  private const val ARTIFACT_WINDOW_CHUNKS = 4
  private const val MAX_ASSEMBLIES = 16
  private const val MAX_ARTIFACT_CACHE = 32
  private const val MAX_OUTBOUND = 16
  private const val EXPECTED_REMOTE_ACKS = 2

  private data class Assembly(
    val artifactId:String, val artifactType:String, val sha:String, val count:Int, val generation:Long,
    val created:Long, val source:InetAddress, var lastNackWallMs:Long=0L,
    var nackBackoffMs:Long=NACK_INTERVAL_MS,
    val chunks:java.util.concurrent.ConcurrentHashMap<Int,ByteArray> = java.util.concurrent.ConcurrentHashMap()
  )
  private data class CachedArtifact(val sha:String,val payload:JSONObject,val completedWallMs:Long,val sourceNode:String="",val generation:Long=0L,val artifactType:String="UNKNOWN")
  private data class OutboundArtifact(
    val artifactId:String,val artifactType:String,val sha:String,val generation:Long,val node:String,val session:String,
    val chunks:List<ByteArray>,var seq:Long,val priority:String="DIAGNOSTIC",val supersedesArtifactId:String?=null,var lastManifestWallMs:Long=0L,var lastFullSendWallMs:Long=0L,var nextChunkIndex:Int=0,var retryBackoffMs:Long=FULL_RETRY_MS,var lastNackSignature:String="",var lastNackWallMs:Long=0L,
    val ackPeers:MutableSet<String> = java.util.concurrent.ConcurrentHashMap.newKeySet(),val lastProgressWallMsByPeer:java.util.concurrent.ConcurrentHashMap<String,Long> = java.util.concurrent.ConcurrentHashMap(),val lastNackSignatureByPeer:java.util.concurrent.ConcurrentHashMap<String,String> = java.util.concurrent.ConcurrentHashMap(),val nackCountByPeer:java.util.concurrent.ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong> = java.util.concurrent.ConcurrentHashMap()
  )
  data class WireReply(val address:InetAddress,val frame:ByteArray)
  data class ConsumeResult(val document:JSONObject?,val replies:List<WireReply>)

  private val assemblies=java.util.concurrent.ConcurrentHashMap<String,Assembly>()
  private val peerDocs=java.util.concurrent.ConcurrentHashMap<String,JSONObject>()
  private val lastAppliedSeq=java.util.concurrent.ConcurrentHashMap<String,Long>()
  private val artifactCache=java.util.LinkedHashMap<String,CachedArtifact>(MAX_ARTIFACT_CACHE,0.75f,true)
  private val outbound=java.util.LinkedHashMap<String,OutboundArtifact>(MAX_OUTBOUND,0.75f,true)
  private val txFramesByType=java.util.concurrent.ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong>()
  private val rxFramesByType=java.util.concurrent.ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong>()
  private val txBytesByType=java.util.concurrent.ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong>()
  private val rxBytesByType=java.util.concurrent.ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong>()
  private val maxBytesByType=java.util.concurrent.ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong>()
  private val maxControlBytesByKey=java.util.concurrent.ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong>()
  private val oversizeControlKeyCounts=java.util.concurrent.ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong>()
  private val criticalControlSendAttempt=java.util.concurrent.ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong>()
  private val criticalControlSendSuccess=java.util.concurrent.ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong>()
  private val criticalControlSendFailure=java.util.concurrent.ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong>()
  private val criticalControlFailureCount=java.util.concurrent.atomic.AtomicLong(0)
  private val optionalControlDropCount=java.util.concurrent.atomic.AtomicLong(0)
  @Volatile private var lastCriticalControlFailureKey:String?=null
  @Volatile private var lastCriticalControlFailureSize:Long=0
  @Volatile private var lastCriticalControlFailureError:String?=null
  @Volatile private var lastOversizeControlKey:String?=null
  @Volatile private var lastOversizeSha256:String?=null
  private val oversizeDropByType=java.util.concurrent.ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong>()
  val requiredFrameOversizeCount=java.util.concurrent.atomic.AtomicLong(0)

  val oversizeBlockCount=java.util.concurrent.atomic.AtomicLong(0)
  val sendErrorCount=java.util.concurrent.atomic.AtomicLong(0)
  val maxDatagramBytesObserved=java.util.concurrent.atomic.AtomicLong(0)
  val txFrames=java.util.concurrent.atomic.AtomicLong(0)
  val rxFrames=java.util.concurrent.atomic.AtomicLong(0)
  val artifactStarted=java.util.concurrent.atomic.AtomicLong(0)
  val artifactCompleted=java.util.concurrent.atomic.AtomicLong(0)
  val artifactFailed=java.util.concurrent.atomic.AtomicLong(0)
  val artifactAckTx=java.util.concurrent.atomic.AtomicLong(0)
  val artifactAckRx=java.util.concurrent.atomic.AtomicLong(0)
  val artifactNackTx=java.util.concurrent.atomic.AtomicLong(0)
  val artifactNackRx=java.util.concurrent.atomic.AtomicLong(0)
  val artifactRetransmitChunks=java.util.concurrent.atomic.AtomicLong(0)
  val artifactDedupChunks=java.util.concurrent.atomic.AtomicLong(0)
  val artifactCacheHits=java.util.concurrent.atomic.AtomicLong(0)
  val artifactCacheEvictions=java.util.concurrent.atomic.AtomicLong(0)
  val artifactOutboundEvictions=java.util.concurrent.atomic.AtomicLong(0)
  val artifactReassemblyTimeouts=java.util.concurrent.atomic.AtomicLong(0)
  val unknownFrameCount=java.util.concurrent.atomic.AtomicLong(0)
  val receiveErrorCount=java.util.concurrent.atomic.AtomicLong(0)
  @Volatile var lastSendError:String?=null
  @Volatile var lastReceiveError:String?=null

  private fun sha(bytes:ByteArray)=java.security.MessageDigest.getInstance("SHA-256").digest(bytes).joinToString(""){"%02x".format(it)}
  private fun crc32(bytes:ByteArray):Long=java.util.zip.CRC32().also{it.update(bytes)}.value
  private fun canonical(v:Any?):String=when(v){
    null,JSONObject.NULL->"null"
    is JSONObject->v.keys().asSequence().toList().sorted().joinToString(prefix="{",postfix="}"){k->JSONObject.quote(k)+":"+canonical(v.opt(k))}
    is JSONArray->(0 until v.length()).joinToString(prefix="[",postfix="]"){i->canonical(v.opt(i))}
    is String->JSONObject.quote(v)
    is Boolean,is Number->v.toString()
    else->JSONObject.quote(v.toString())
  }
  private fun mapJson(m:java.util.concurrent.ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong>):JSONObject {
    val o=JSONObject();m.keys.sorted().forEach{k->o.put(k,m[k]?.get()?:0L)};return o
  }
  private fun envelope(type:String,node:String,session:String,seq:Long,body:(JSONObject)->Unit):ByteArray {
    val o=JSONObject().put("schema","WireEnvelopeV10").put("message_type",type).put("session_id",session).put("node_id",node).put("seq",seq)
    body(o)
    var b=o.toString().toByteArray(Charsets.UTF_8)
    o.put("wire_payload_bytes",b.size)
    b=o.toString().toByteArray(Charsets.UTF_8)
    o.put("wire_payload_bytes",b.size)
    b=o.toString().toByteArray(Charsets.UTF_8)
    maxDatagramBytesObserved.updateAndGet{v->kotlin.math.max(v,b.size.toLong())}
    maxBytesByType.computeIfAbsent(type){java.util.concurrent.atomic.AtomicLong(0)}.updateAndGet{v->kotlin.math.max(v,b.size.toLong())}
    if(type=="RANGE_FRAME" && b.size>RANGE_FRAME_TARGET_BYTES){requiredFrameOversizeCount.incrementAndGet();oversizeBlockCount.incrementAndGet();oversizeDropByType.computeIfAbsent(type){java.util.concurrent.atomic.AtomicLong(0)}.incrementAndGet();throw IllegalStateException("WIRE_OVERSIZE_RANGE_FRAME_${b.size}")}
    if(type=="CONTROL_FRAME" && b.size>CONTROL_FRAME_TARGET_BYTES){requiredFrameOversizeCount.incrementAndGet();oversizeBlockCount.incrementAndGet();oversizeDropByType.computeIfAbsent(type){java.util.concurrent.atomic.AtomicLong(0)}.incrementAndGet();throw IllegalStateException("WIRE_OVERSIZE_CONTROL_FRAME_${b.size}")}
    if(b.size>MAX_DATAGRAM_BYTES){if(type in listOf("RANGE_FRAME","CONTROL_FRAME","GEOMETRY_FRAME","GEOMETRY_POSITION_FRAME"))requiredFrameOversizeCount.incrementAndGet();oversizeBlockCount.incrementAndGet();oversizeDropByType.computeIfAbsent(type){java.util.concurrent.atomic.AtomicLong(0)}.incrementAndGet();throw IllegalStateException("WIRE_OVERSIZE_${type}_${b.size}")}
    return b
  }
  private fun safeAdd(out:MutableList<ByteArray>,type:String,node:String,session:String,seq:Long,body:(JSONObject)->Unit){
    try{out+=envelope(type,node,session,seq,body)}catch(t:Throwable){lastSendError="${t.javaClass.simpleName}:${t.message}"}
  }
  private val criticalControlKeys=setOf("authority_view_v1","authority_ack_v1","calibration_meta_v10","calibration_ack_v10","decision_meta_v10","decision_ack_v10","scenario_command_v1","scenario_ack_v1","run_start_prepare_v1","run_start_ready_v1","run_start_commit_v1","run_freeze_prepare_v2","snapshot_ready_v2","run_freeze_commit_v2")
  private fun safeAddControl(out:MutableList<ByteArray>,key:String,value:Any?,node:String,session:String,seq:Long){
    val critical=criticalControlKeys.contains(key);if(critical)criticalControlSendAttempt.computeIfAbsent(key){AtomicLong(0)}.incrementAndGet()
    val compact=JSONObject().put("control_key",key).put("control_value",value).toString().toByteArray(Charsets.UTF_8)
    if(compact.size>COMPACT_CONTROL_PAYLOAD_TARGET_BYTES){oversizeControlKeyCounts.computeIfAbsent(key){AtomicLong(0)}.incrementAndGet();lastOversizeControlKey=key;lastOversizeSha256=sha(compact);if(critical){criticalControlFailureCount.incrementAndGet();criticalControlSendFailure.computeIfAbsent(key){AtomicLong(0)}.incrementAndGet();lastCriticalControlFailureKey=key;lastCriticalControlFailureSize=compact.size.toLong();lastCriticalControlFailureError="CRITICAL_CONTROL_PAYLOAD_OVER_600";safeAdd(out,"CONTROL_FATAL",node,session,seq){o->o.put("control_key",key).put("payload_sha256",sha(compact)).put("payload_bytes",compact.size).put("fatal",true)}}else optionalControlDropCount.incrementAndGet();return}
    try{val frame=envelope("CONTROL_FRAME",node,session,seq){o->o.put("control_key",key).put("control_value",value)};if(frame.size>CONTROL_FRAME_TARGET_BYTES)throw IllegalArgumentException("CONTROL_FRAME_OVER_900:${frame.size}");maxControlBytesByKey.computeIfAbsent(key){AtomicLong(0)}.updateAndGet{v->kotlin.math.max(v,frame.size.toLong())};out+=frame;if(critical)criticalControlSendSuccess.computeIfAbsent(key){AtomicLong(0)}.incrementAndGet()}catch(t:Throwable){oversizeControlKeyCounts.computeIfAbsent(key){AtomicLong(0)}.incrementAndGet();lastOversizeControlKey=key;lastOversizeSha256=sha(compact);if(critical){criticalControlFailureCount.incrementAndGet();criticalControlSendFailure.computeIfAbsent(key){AtomicLong(0)}.incrementAndGet();lastCriticalControlFailureKey=key;lastCriticalControlFailureSize=compact.size.toLong();lastCriticalControlFailureError="${t.javaClass.simpleName}:${t.message}"}else optionalControlDropCount.incrementAndGet();lastSendError="${t.javaClass.simpleName}:${t.message}"}
  }
  @Synchronized private fun putArtifactCache(id:String,value:CachedArtifact){
    artifactCache[id]=value
    while(artifactCache.size>MAX_ARTIFACT_CACHE){val it=artifactCache.entries.iterator();if(it.hasNext()){it.next();it.remove();artifactCacheEvictions.incrementAndGet()}else break}
  }
  @Synchronized private fun cachedArtifact(id:String):CachedArtifact?=artifactCache[id]
  @Synchronized private fun putOutbound(value:OutboundArtifact){
    outbound[value.artifactId]=value
    while(outbound.size>MAX_OUTBOUND){val it=outbound.entries.iterator();if(it.hasNext()){it.next();it.remove();artifactOutboundEvictions.incrementAndGet()}else break}
  }
  @Synchronized private fun outboundArtifact(id:String):OutboundArtifact?=outbound[id]
  private fun doc(node:String,session:String):JSONObject=peerDocs.computeIfAbsent(node){JSONObject().put("protocol_version",2).put("session_id",session).put("node_id",node).put("ranges",JSONArray()).put("control_plane",JSONObject()).put("artifact_cache_v1",JSONObject())}
  private fun applyDedup(o:JSONObject,subkey:String=""):Boolean{
    val type=o.optString("message_type");if(type.startsWith("ARTIFACT_"))return true
    val key="${o.optString("node_id")}|$type|$subkey";val seq=o.optLong("seq",0L);val prior=lastAppliedSeq[key]
    if(prior!=null&&seq<=prior)return false;lastAppliedSeq[key]=seq;return true
  }
  private fun updateRange(d:JSONObject,r:JSONObject){
    val arr=d.optJSONArray("ranges")?:JSONArray();val key="${r.optString("observer_node_id")}::${r.optString("peer_node_id")}";val next=JSONArray();var replaced=false
    for(i in 0 until arr.length()){val x=arr.optJSONObject(i)?:continue;val k="${x.optString("observer_node_id")}::${x.optString("peer_node_id")}";if(k==key){next.put(r);replaced=true}else next.put(x)}
    if(!replaced)next.put(r);d.put("ranges",next)
  }
  private fun updateGeometryPosition(d:JSONObject,p:JSONObject){
    val g=d.optJSONObject("published_geometry")?:JSONObject().put("positions",JSONArray());val arr=g.optJSONArray("positions")?:JSONArray();val id=p.optString("node_id");val next=JSONArray();var replaced=false
    for(i in 0 until arr.length()){val x=arr.optJSONObject(i)?:continue;if(x.optString("node_id")==id){next.put(p);replaced=true}else next.put(x)}
    if(!replaced)next.put(p);g.put("positions",next);d.put("published_geometry",g)
  }
  private fun registerArtifact(item:JSONObject,node:String,session:String,seq:Long):OutboundArtifact?{
    val id=item.optString("artifact_id");val type=item.optString("artifact_type");val payload=item.opt("payload")
    if(id.isBlank()||type.isBlank()||payload==null||payload===JSONObject.NULL)return null
    val bytes=canonical(payload).toByteArray(Charsets.UTF_8);val digest=sha(bytes);val chunks=bytes.toList().chunked(CHUNK_BYTES).map{it.toByteArray()};if(chunks.isEmpty())return null
    val existing=outboundArtifact(id);if(existing!=null&&existing.sha==digest){existing.seq=seq;return existing}
    val generation=item.optLong("generation",0L);val priority=item.optString("priority","DIAGNOSTIC");val supersedes=item.optString("supersedes_artifact_id").takeIf{it.isNotBlank()};synchronized(this){outbound.values.filter{it.artifactType==type&&it.artifactId!=id&&it.generation<=generation}.map{it.artifactId}.forEach{outbound.remove(it)}};return OutboundArtifact(id,type,digest,generation,node,session,chunks,seq,priority,supersedes).also{putOutbound(it)}
  }
  private fun manifestFrame(a:OutboundArtifact)=envelope("ARTIFACT_MANIFEST",a.node,a.session,a.seq){it.put("schema","ArtifactManifestV4").put("artifact_id",a.artifactId).put("artifact_type",a.artifactType).put("artifact_sha256",a.sha).put("artifact_size",a.chunks.sumOf{x->x.size}).put("chunk_count",a.chunks.size).put("generation",a.generation).put("priority",a.priority).put("supersedes_artifact_id",a.supersedesArtifactId?:JSONObject.NULL)}
  private fun chunkFrame(a:OutboundArtifact,index:Int,seq:Long=a.seq)=envelope("ARTIFACT_CHUNK",a.node,a.session,seq){val c=a.chunks[index];it.put("artifact_id",a.artifactId).put("artifact_sha256",a.sha).put("chunk_index",index).put("chunk_count",a.chunks.size).put("payload_crc32",crc32(c)).put("payload_b64",android.util.Base64.encodeToString(c,android.util.Base64.NO_WRAP))}
  private fun ackFrame(id:String,digest:String,seq:Long)=envelope("ARTIFACT_ACK",FabricRuntime.nodeId,FabricRuntime.sessionId,seq){it.put("artifact_id",id).put("artifact_sha256",digest).put("complete",true)}
  private fun nackFrame(id:String,digest:String,missing:List<Int>,seq:Long)=envelope("ARTIFACT_NACK",FabricRuntime.nodeId,FabricRuntime.sessionId,seq){it.put("artifact_id",id).put("artifact_sha256",digest).put("missing_chunks",JSONArray(missing.take(ARTIFACT_WINDOW_CHUNKS)))}

  fun frames(advertisement:JSONObject,node:String,session:String,seq:Long):List<ByteArray>{
    val out=mutableListOf<ByteArray>()
    safeAdd(out,"HEARTBEAT",node,session,seq){o->
      for(k in listOf("protocol_version","instance_epoch","display_name","platform","coordinator_score","rssi_dbm","baseline_rssi_dbm","baseline_sigma_db","scanning","ble_identity","manual_geometry_override"))if(advertisement.has(k))o.put(k,advertisement.opt(k))
    }
    val ranges=advertisement.optJSONArray("ranges")?:JSONArray()
    for(i in 0 until ranges.length()){val r=ranges.optJSONObject(i)?:continue;val sub="${r.optString("observer_node_id")}::${r.optString("peer_node_id")}";val senderNow=advertisement.optLong("monotonic_ns",0L);val observationMono=r.optLong("monotonic_ns",0L);val senderAge=if(senderNow>0L&&observationMono>0L)kotlin.math.max(0L,(senderNow-observationMono)/1_000_000L) else r.optLong("range_age_ms",0L);safeAdd(out,"RANGE_FRAME",node,session,seq){o->o.put("range_key",sub).put("instance_epoch",FabricRuntime.instanceEpoch).put("observer_node_id",r.optString("observer_node_id")).put("peer_node_id",r.optString("peer_node_id")).put("technology",r.optString("technology")).put("sender_range_age_ms",senderAge).put("sender_temporal_state",r.optString("range_temporal_state","FRESH")).put("sender_sequence",seq).put("distance_m",r.opt("distance_m")).put("distance_sigma_m",r.opt("distance_sigma_m")).put("rssi_dbm",r.opt("rssi_dbm")).put("quality",r.optString("quality","LOW")).put("range_domain_state",r.optString("range_temporal_state","FRESH")).put("range_status",r.optString("range_status","UNKNOWN"))}}
    val cp=advertisement.optJSONObject("control_plane")
    val artifacts=mutableMapOf<String,OutboundArtifact>()
    if(cp!=null){
      val payloads=cp.optJSONArray("artifact_payloads_v1")?:JSONArray()
      for(i in 0 until payloads.length()){val item=payloads.optJSONObject(i)?:continue;registerArtifact(item,node,session,seq)?.let{artifacts[it.artifactId]=it}}
      val meta=JSONObject();for(k in listOf("schema","session_id","node_id"))if(cp.has(k))meta.put(k,cp.opt(k));safeAddControl(out,"__meta__",meta,node,session,seq)
      for(k in listOf("authority_view_v1","authority_ack_v1","logical_membership_state","calibration_meta_v10","calibration_ack_v10","decision_meta_v10","decision_ack_v10","scenario_command_v1","scenario_ack_v1","run_start_prepare_v1","run_start_ready_v1","run_start_commit_v1","run_freeze_prepare_v2","snapshot_ready_v2","run_freeze_commit_v2")){
        if(!cp.has(k)||cp.isNull(k))continue;val value=cp.opt(k);val copy=if(value is JSONObject)JSONObject(value.toString())else value
        if(copy is JSONObject){val id=copy.optString("calibration_artifact_id").ifBlank{copy.optString("decision_artifact_id")};artifacts[id]?.let{copy.put("artifact_sha256",it.sha)}}
        safeAddControl(out,k,copy,node,session,seq)
      }
      val now=System.currentTimeMillis()
      for(a in artifacts.values){if(a.ackPeers.size<EXPECTED_REMOTE_ACKS&&now-a.lastManifestWallMs>=2_000L){try{out+=manifestFrame(a);a.lastManifestWallMs=now}catch(t:Throwable){lastSendError="${t.javaClass.simpleName}:${t.message}"}}}
      val rank=mapOf("CALIBRATION" to 0,"DECISION_FINAL" to 1,"DECISION_LIVE" to 2,"DIAGNOSTIC" to 3);val a=artifacts.values.filter{it.ackPeers.size<EXPECTED_REMOTE_ACKS&&now-it.lastFullSendWallMs>=it.retryBackoffMs}.sortedWith(compareBy<OutboundArtifact>{rank[it.priority]?:9}.thenByDescending{it.generation}).firstOrNull();if(a!=null){val end=(a.nextChunkIndex+ARTIFACT_WINDOW_CHUNKS).coerceAtMost(a.chunks.size);for(i in a.nextChunkIndex until end)try{out+=chunkFrame(a,i)}catch(t:Throwable){lastSendError="${t.javaClass.simpleName}:${t.message}"};a.nextChunkIndex=if(end>=a.chunks.size)0 else end;if(a.nextChunkIndex==0)a.retryBackoffMs=(a.retryBackoffMs*2).coerceAtMost(MAX_RETRY_BACKOFF_MS);a.lastFullSendWallMs=now}
    }
    val g=advertisement.optJSONObject("published_geometry")
    if(g!=null){
      val meta=JSONObject();for(k in listOf("frame_id","revision","generated_monotonic_ns","dimension","state","anchor_node_id","axis_node_id","residual_rms_m","condition_score","reason"))if(g.has(k))meta.put(k,g.opt(k));safeAdd(out,"GEOMETRY_FRAME",node,session,seq){o->o.put("geometry",meta)}
      val positions=g.optJSONArray("positions")?:JSONArray();for(i in 0 until positions.length()){val p=positions.optJSONObject(i)?:continue;safeAdd(out,"GEOMETRY_POSITION_FRAME",node,session,seq){o->o.put("position",p)}}
    }
    val priority=mapOf("HEARTBEAT" to 0,"RANGE_FRAME" to 1,"GEOMETRY_FRAME" to 2,"GEOMETRY_POSITION_FRAME" to 3,"CONTROL_FRAME" to 4,"ARTIFACT_MANIFEST" to 5,"ARTIFACT_ACK" to 6,"ARTIFACT_NACK" to 6,"ARTIFACT_CHUNK" to 7);return out.sortedBy{priority[frameType(it)]?:9}
  }
  private fun frameType(frame:ByteArray):String=try{JSONObject(String(frame,Charsets.UTF_8)).optString("message_type","UNKNOWN")}catch(_:Throwable){"UNKNOWN"}
  fun send(socket:MulticastSocket,address:InetAddress,port:Int,frames:List<ByteArray>){
    for(frame in frames){
      if(frame.size>MAX_DATAGRAM_BYTES){oversizeBlockCount.incrementAndGet();continue};val type=frameType(frame)
      try{socket.send(DatagramPacket(frame,frame.size,address,port));txFrames.incrementAndGet();FabricRuntime.txPackets.incrementAndGet();txFramesByType.computeIfAbsent(type){java.util.concurrent.atomic.AtomicLong(0)}.incrementAndGet();txBytesByType.computeIfAbsent(type){java.util.concurrent.atomic.AtomicLong(0)}.addAndGet(frame.size.toLong())}catch(t:Throwable){sendErrorCount.incrementAndGet();lastSendError="${t.javaClass.simpleName}:${t.message}"}
    }
  }
  private fun missing(a:Assembly)= (0 until a.count).filter{!a.chunks.containsKey(it)}
  private fun reply(address:InetAddress,frame:ByteArray)=WireReply(address,frame)
  private fun artifactDoc(node:String,session:String,id:String,payload:JSONObject,sha:String,generation:Long=0L,artifactType:String="UNKNOWN"):JSONObject{
    val d=doc(node,session);val cache=d.optJSONObject("artifact_cache_v1")?:JSONObject();cache.put(id,payload);d.put("artifact_cache_v1",cache);val meta=d.optJSONObject("artifact_cache_meta_v1")?:JSONObject();meta.put(id,JSONObject().put("artifact_sha256",sha).put("complete",true).put("source_node_id",node).put("source_generation",generation).put("artifact_type",artifactType));d.put("artifact_cache_meta_v1",meta);return d
  }
  fun consume(text:String,source:InetAddress):ConsumeResult{
    val o=try{JSONObject(text)}catch(t:Throwable){receiveErrorCount.incrementAndGet();lastReceiveError="${t.javaClass.simpleName}:${t.message}";return ConsumeResult(null,emptyList())}
    if(o.optString("schema")!="WireEnvelopeV10")return ConsumeResult(o,emptyList())
    val bytes=text.toByteArray(Charsets.UTF_8);val type=o.optString("message_type");rxFrames.incrementAndGet();rxFramesByType.computeIfAbsent(type){java.util.concurrent.atomic.AtomicLong(0)}.incrementAndGet();rxBytesByType.computeIfAbsent(type){java.util.concurrent.atomic.AtomicLong(0)}.addAndGet(bytes.size.toLong());maxDatagramBytesObserved.updateAndGet{v->kotlin.math.max(v,bytes.size.toLong())}
    if(bytes.size>MAX_DATAGRAM_BYTES){oversizeBlockCount.incrementAndGet();return ConsumeResult(null,emptyList())}
    val session=o.optString("session_id");if(session!=FabricRuntime.sessionId)return ConsumeResult(null,emptyList());val node=o.optString("node_id");if(node.isBlank()||node==FabricRuntime.nodeId)return ConsumeResult(null,emptyList());val seq=o.optLong("seq",0L);val now=System.currentTimeMillis();val replies=mutableListOf<WireReply>()
    when(type){
      "HEARTBEAT"->{if(!applyDedup(o))return ConsumeResult(null,emptyList());val d=doc(node,session);for(k in listOf("protocol_version","instance_epoch","display_name","platform","coordinator_score","rssi_dbm","baseline_rssi_dbm","baseline_sigma_db","scanning","ble_identity","manual_geometry_override"))if(o.has(k))d.put(k,o.opt(k));return ConsumeResult(d,replies)}
      "RANGE_FRAME"->{val key=o.optString("range_key");if(!applyDedup(o,key))return ConsumeResult(null,emptyList());val receiveMono=SystemClock.elapsedRealtimeNanos();val senderAge=o.optLong("sender_range_age_ms",-1L);if(senderAge<0L)return ConsumeResult(null,emptyList());val r=JSONObject().put("session_id",session).put("observer_node_id",o.optString("observer_node_id",node)).put("peer_node_id",o.optString("peer_node_id")).put("technology",o.optString("technology")).put("monotonic_ns",0L).put("sender_range_age_ms",senderAge).put("sender_temporal_state",o.optString("sender_temporal_state","FRESH")).put("sender_sequence",o.optLong("sender_sequence",seq)).put("instance_epoch",o.optString("instance_epoch")).put("received_local_monotonic_ns",receiveMono).put("effective_age_ms",senderAge).put("distance_m",o.opt("distance_m")).put("distance_sigma_m",o.opt("distance_sigma_m")).put("rssi_dbm",o.opt("rssi_dbm")).put("quality",o.optString("quality","LOW")).put("range_domain_state",o.optString("range_domain_state","FRESH")).put("range_status",o.optString("range_status","UNKNOWN")).put("source_detail","WireEnvelopeV10 compact range; foreign monotonic excluded from freshness arithmetic");val d=doc(node,session);d.put("instance_epoch",o.optString("instance_epoch"));updateRange(d,r);return ConsumeResult(d,replies)}
      "CONTROL_FRAME"->{val key=o.optString("control_key");if(!applyDedup(o,key))return ConsumeResult(null,emptyList());val d=doc(node,session);val cp=d.optJSONObject("control_plane")?:JSONObject();val value=o.opt("control_value");if(key=="__meta__"&&value is JSONObject){value.keys().forEach{k->cp.put(k,value.opt(k))}}else cp.put(key,value);d.put("control_plane",cp);return ConsumeResult(d,replies)}
      "GEOMETRY_FRAME"->{if(!applyDedup(o,"meta"))return ConsumeResult(null,emptyList());val d=doc(node,session);val g=o.optJSONObject("geometry")?:JSONObject();val existing=d.optJSONObject("published_geometry");if(existing!=null&&existing.has("positions"))g.put("positions",existing.optJSONArray("positions"));d.put("geometry_publisher_node_id",node);g.put("schema","GeometryPublicationV11").put("publication_lease_ms",GEOMETRY_PUBLICATION_LEASE_MS).put("publisher_node_id",node).put("publisher_instance_epoch",o.optString("instance_epoch")).put("publication_session_id",session).put("publication_sequence",seq).put("received_local_monotonic_ns",SystemClock.elapsedRealtimeNanos());d.put("published_geometry",g);return ConsumeResult(d,replies)}
      "GEOMETRY_POSITION_FRAME"->{val p=o.optJSONObject("position")?:return ConsumeResult(null,emptyList());if(!applyDedup(o,p.optString("node_id")))return ConsumeResult(null,emptyList());val d=doc(node,session);updateGeometryPosition(d,p);return ConsumeResult(d,replies)}
      "ARTIFACT_MANIFEST"->{val id=o.optString("artifact_id");val digest=o.optString("artifact_sha256");val count=o.optInt("chunk_count");if(id.isBlank()||digest.isBlank()||count<=0||count>4096)return ConsumeResult(null,emptyList());val cached=cachedArtifact(id);if(cached!=null&&cached.sha==digest){artifactCacheHits.incrementAndGet();artifactAckTx.incrementAndGet();replies+=reply(source,ackFrame(id,digest,now));return ConsumeResult(artifactDoc(node,session,id,cached.payload,digest),replies)};val incomingType=o.optString("artifact_type");val incomingGeneration=o.optLong("generation",0L);assemblies.entries.filter{it.value.artifactType==incomingType&&it.value.generation<=incomingGeneration&&it.key!=id}.forEach{assemblies.remove(it.key)};assemblies.computeIfAbsent(id){artifactStarted.incrementAndGet();Assembly(id,incomingType,digest,count,incomingGeneration,now,source)};return ConsumeResult(null,replies)}
      "ARTIFACT_CHUNK"->{val id=o.optString("artifact_id");val digest=o.optString("artifact_sha256");val count=o.optInt("chunk_count");val idx=o.optInt("chunk_index",-1);if(id.isBlank()||digest.isBlank()||idx !in 0 until count)return ConsumeResult(null,emptyList());val a=assemblies.computeIfAbsent(id){artifactStarted.incrementAndGet();Assembly(id,"UNKNOWN",digest,count,0L,now,source)};if(a.sha!=digest||a.count!=count){artifactFailed.incrementAndGet();return ConsumeResult(null,replies)};val chunk=try{android.util.Base64.decode(o.optString("payload_b64"),android.util.Base64.DEFAULT)}catch(_:Throwable){byteArrayOf()};if(chunk.size>CHUNK_BYTES||crc32(chunk)!=o.optLong("payload_crc32",-1L)){artifactFailed.incrementAndGet();artifactNackTx.incrementAndGet();replies+=reply(source,nackFrame(id,digest,listOf(idx),now));return ConsumeResult(null,replies)};if(a.chunks.putIfAbsent(idx,chunk)!=null)artifactDedupChunks.incrementAndGet() else a.nackBackoffMs=NACK_INTERVAL_MS;if(a.chunks.size==a.count){val payload=(0 until a.count).flatMap{(a.chunks[it]?:byteArrayOf()).toList()}.toByteArray();assemblies.remove(id);if(sha(payload)!=a.sha){artifactFailed.incrementAndGet();artifactNackTx.incrementAndGet();replies+=reply(source,nackFrame(id,digest,(0 until count).toList(),now));return ConsumeResult(null,replies)};val obj=try{JSONObject(String(payload,Charsets.UTF_8))}catch(_:Throwable){artifactFailed.incrementAndGet();return ConsumeResult(null,replies)};putArtifactCache(id,CachedArtifact(digest,obj,now,node,a.generation,a.artifactType));artifactCompleted.incrementAndGet();artifactAckTx.incrementAndGet();replies+=reply(source,ackFrame(id,digest,now));return ConsumeResult(artifactDoc(node,session,id,obj,digest,a.generation,a.artifactType),replies)};if(idx==count-1){val miss=missing(a);if(miss.isNotEmpty()){a.lastNackWallMs=now;artifactNackTx.incrementAndGet();replies+=reply(source,nackFrame(id,digest,miss,now))}};return ConsumeResult(null,replies)}
      "ARTIFACT_ACK"->{artifactAckRx.incrementAndGet();val id=o.optString("artifact_id");val a=outboundArtifact(id);if(a!=null&&a.sha==o.optString("artifact_sha256")){a.ackPeers.add(node);a.lastProgressWallMsByPeer[node]=now;a.retryBackoffMs=FULL_RETRY_MS};return ConsumeResult(null,replies)}
      "ARTIFACT_NACK"->{artifactNackRx.incrementAndGet();val id=o.optString("artifact_id");val a=outboundArtifact(id)?:return ConsumeResult(null,replies);if(a.sha!=o.optString("artifact_sha256"))return ConsumeResult(null,replies);val miss=o.optJSONArray("missing_chunks")?:JSONArray();val requested=(0 until miss.length()).map{miss.optInt(it,-1)}.filter{it in a.chunks.indices}.distinct().sorted();val sig=requested.joinToString(",");if(sig==a.lastNackSignature&&now-a.lastNackWallMs<NACK_INTERVAL_MS)return ConsumeResult(null,replies);a.lastNackSignature=sig;a.lastNackWallMs=now;a.lastNackSignatureByPeer[node]=sig;a.lastProgressWallMsByPeer[node]=now;a.nackCountByPeer.computeIfAbsent(node){AtomicLong(0)}.incrementAndGet();a.retryBackoffMs=FULL_RETRY_MS;for(idx in requested.take(ARTIFACT_WINDOW_CHUNKS)){artifactRetransmitChunks.incrementAndGet();replies+=reply(source,chunkFrame(a,idx,now))};return ConsumeResult(null,replies)}
      else->{unknownFrameCount.incrementAndGet();return ConsumeResult(null,replies)}
    }
  }
  fun maintenance(now:Long):List<WireReply>{
    val replies=mutableListOf<WireReply>();val entries=assemblies.entries.toList().sortedBy{it.value.created}
    if(entries.size>MAX_ASSEMBLIES)for(e in entries.take(entries.size-MAX_ASSEMBLIES)){if(assemblies.remove(e.key)!=null){artifactFailed.incrementAndGet();artifactReassemblyTimeouts.incrementAndGet()}}
    for((id,a) in assemblies.entries){val age=now-a.created;if(age>ASSEMBLY_TIMEOUT_MS){val miss=missing(a);if(miss.isNotEmpty()&&now-a.lastNackWallMs>=NACK_INTERVAL_MS){a.lastNackWallMs=now;artifactNackTx.incrementAndGet();replies+=reply(a.source,nackFrame(id,a.sha,miss,now));continue};if(assemblies.remove(id)!=null){artifactFailed.incrementAndGet();artifactReassemblyTimeouts.incrementAndGet()};continue};if(now-a.lastNackWallMs>=a.nackBackoffMs&&age>=NACK_INTERVAL_MS){val miss=missing(a);if(miss.isNotEmpty()){a.lastNackWallMs=now;a.nackBackoffMs=(a.nackBackoffMs*2).coerceAtMost(8_000L);artifactNackTx.incrementAndGet();replies+=reply(a.source,nackFrame(id,a.sha,miss,now))}}}
    return replies
  }
  fun noteReceiveError(t:Throwable){receiveErrorCount.incrementAndGet();lastReceiveError="${t.javaClass.simpleName}:${t.message}"}
  @Synchronized private fun artifactPeerStateJson():JSONObject{val root=JSONObject();outbound.values.forEach{a->val peers=JSONObject();val ids=(a.lastProgressWallMsByPeer.keys+a.ackPeers).toSet().sorted();ids.forEach{id->peers.put(id,JSONObject().put("complete",a.ackPeers.contains(id)).put("last_progress_wall_ms",a.lastProgressWallMsByPeer[id]?:JSONObject.NULL).put("last_nack_signature",a.lastNackSignatureByPeer[id]?:JSONObject.NULL).put("nack_count",a.nackCountByPeer[id]?.get()?:0L))};root.put(a.artifactId,JSONObject().put("artifact_type",a.artifactType).put("generation",a.generation).put("manifest_pending",a.ackPeers.size<EXPECTED_REMOTE_ACKS).put("acked_peer_count",a.ackPeers.size).put("retry_backoff_ms",a.retryBackoffMs).put("peers",peers))};return root}
  @Synchronized private fun artifactReceiverStateJson():JSONObject{val root=JSONObject();assemblies.values.sortedBy{it.artifactId}.forEach{a->root.put(a.artifactId,JSONObject().put("artifact_type",a.artifactType).put("generation",a.generation).put("chunk_count",a.count).put("received_chunks",a.chunks.size).put("missing_chunks",JSONArray(missing(a))).put("last_nack_wall_ms",a.lastNackWallMs).put("nack_backoff_ms",a.nackBackoffMs))};return root}
  fun telemetry()=JSONObject()
    .put("schema","WireTransportTelemetryV13").put("max_datagram_budget_bytes",MAX_DATAGRAM_BYTES).put("range_frame_target_bytes",RANGE_FRAME_TARGET_BYTES).put("control_frame_target_bytes",CONTROL_FRAME_TARGET_BYTES).put("chunk_payload_bytes",CHUNK_BYTES).put("artifact_window_chunks",ARTIFACT_WINDOW_CHUNKS)
    .put("critical_control_payload_target_bytes",COMPACT_CONTROL_PAYLOAD_TARGET_BYTES).put("critical_control_failure_count",criticalControlFailureCount.get()).put("optional_control_drop_count",optionalControlDropCount.get()).put("critical_control_send_attempt",mapJson(criticalControlSendAttempt)).put("critical_control_send_success",mapJson(criticalControlSendSuccess)).put("critical_control_send_failure",mapJson(criticalControlSendFailure)).put("last_critical_control_failure_key",lastCriticalControlFailureKey?:JSONObject.NULL).put("last_critical_control_failure_size",lastCriticalControlFailureSize).put("last_critical_control_failure_error",lastCriticalControlFailureError?:JSONObject.NULL)
    .put("max_datagram_bytes_observed",maxDatagramBytesObserved.get()).put("max_datagram_bytes_by_type",mapJson(maxBytesByType)).put("oversize_drop_by_type",mapJson(oversizeDropByType)).put("wire_oversize_block_count",oversizeBlockCount.get()).put("required_frame_oversize_count",requiredFrameOversizeCount.get()).put("max_control_bytes_by_key",mapJson(maxControlBytesByKey)).put("oversize_control_key_counts",mapJson(oversizeControlKeyCounts)).put("last_oversize_control_key",lastOversizeControlKey?:JSONObject.NULL).put("last_oversize_sha256",lastOversizeSha256?:JSONObject.NULL)
    .put("wire_send_error_count",sendErrorCount.get()).put("wire_last_send_error",lastSendError?:JSONObject.NULL).put("wire_receive_error_count",receiveErrorCount.get()).put("wire_last_receive_error",lastReceiveError?:JSONObject.NULL)
    .put("tx_frames",txFrames.get()).put("rx_frames",rxFrames.get()).put("tx_frames_by_type",mapJson(txFramesByType)).put("rx_frames_by_type",mapJson(rxFramesByType)).put("tx_bytes_by_type",mapJson(txBytesByType)).put("rx_bytes_by_type",mapJson(rxBytesByType))
    .put("artifact_peer_state_v1",artifactPeerStateJson()).put("artifact_receiver_state_v1",artifactReceiverStateJson()).put("artifact_transfer_started",artifactStarted.get()).put("artifact_transfer_completed",artifactCompleted.get()).put("artifact_transfer_failed",artifactFailed.get()).put("artifact_reassembly_pending",assemblies.size)
    .put("artifact_ack_tx",artifactAckTx.get()).put("artifact_ack_rx",artifactAckRx.get()).put("artifact_nack_tx",artifactNackTx.get()).put("artifact_nack_rx",artifactNackRx.get()).put("artifact_retransmit_chunks",artifactRetransmitChunks.get()).put("artifact_dedup_chunks",artifactDedupChunks.get())
    .put("artifact_cache_size",synchronized(this){artifactCache.size}).put("artifact_cache_hits",artifactCacheHits.get()).put("artifact_cache_evictions",artifactCacheEvictions.get()).put("artifact_outbound_cache_size",synchronized(this){outbound.size}).put("artifact_outbound_evictions",artifactOutboundEvictions.get()).put("artifact_reassembly_timeouts",artifactReassemblyTimeouts.get()).put("unknown_frame_count",unknownFrameCount.get())
}

private object FabricRuntime {
  @Volatile var running = false
  @Volatile var nodeId = UUID.randomUUID().toString()
  @Volatile var instanceEpoch = UUID.randomUUID().toString()
  @Volatile var displayName = Build.MODEL ?: "Android"
  @Volatile var sessionId = "body-finder-lab"
  @Volatile var baseline: Double? = null
  @Volatile var sigma: Double? = null
  @Volatile var scanning = false
  @Volatile var bleScanning = false
  @Volatile var bleAdvertising = false
  @Volatile var bleDetail = "BLE not started"
  @Volatile var bleScanState = "IDLE"
  @Volatile var bleAdvertiseState = "IDLE"
  @Volatile var bleScanMode = "NONE"
  @Volatile var bleScanFailureCode: Int? = null
  @Volatile var bleAdvertiseFailureCode: Int? = null
  @Volatile var bleAdvertiseStartedWallMs: Long? = null
  @Volatile var bleScanStartedWallMs: Long? = null
  @Volatile var socketState = "IDLE"
  @Volatile var multicastJoinState = "IDLE"
  @Volatile var publishedGeometryJson: String? = null
  @Volatile var controlPlaneJson: String? = null
  @Volatile var lastScanRestartWallMs: Long = 0L
  val scanGeneration = AtomicLong(0)

  var socket: MulticastSocket? = null
  var advertiser: android.bluetooth.le.BluetoothLeAdvertiser? = null
  var scanner: android.bluetooth.le.BluetoothLeScanner? = null
  var advertiseCallback: AdvertiseCallback? = null
  var scanCallback: ScanCallback? = null

  val peers = ConcurrentHashMap<String, Pair<String, Long>>()
  val peerPacketCounts = ConcurrentHashMap<String, AtomicLong>()
  val peerLastSeenWallMs = ConcurrentHashMap<String, Long>()
  val peerLastSeenMonotonicNs = ConcurrentHashMap<String, Long>()
  val peerStaleSinceWallMs = ConcurrentHashMap<String, Long>()
  val rssiWindows = ConcurrentHashMap<String, ConcurrentLinkedDeque<RssiSample>>()
  val invalidRssiEventsByIdentity = ConcurrentHashMap<String, ConcurrentLinkedDeque<InvalidRssiEvent>>()
  val invalidRssiCountByIdentity = ConcurrentHashMap<String, AtomicLong>()
  val lastValidRssiWallMsByIdentity = ConcurrentHashMap<String, Long>()
  val lastInvalidRssiWallMsByIdentity = ConcurrentHashMap<String, Long>()
  val lastInvalidRssiValueByIdentity = ConcurrentHashMap<String, Int>()
  val lastValidRangeByPeer = ConcurrentHashMap<String, LastValidRangeState>()
  val bleAddressByIdentity = ConcurrentHashMap<String, String>()
  val bleLastSeenWallMsByIdentity = ConcurrentHashMap<String, Long>()
  val bleSeenCountByIdentity = ConcurrentHashMap<String, AtomicLong>()
  val acquisitionStatsByIdentity = ConcurrentHashMap<String, BleAcquisitionStats>()
  val validationAcquisitionBaselineByIdentity = ConcurrentHashMap<String, BleAcquisitionCounterSnapshot>()
  val peerHealthStateByPeer = ConcurrentHashMap<String, String>()
  val starvationCandidateSinceByPeer = ConcurrentHashMap<String, Long>()
  val starvationSinceByPeer = ConcurrentHashMap<String, Long>()
  val peerStarvationCountByPeer = ConcurrentHashMap<String, AtomicLong>()
  val peerStarvationRecoveryParticipationByPeer = ConcurrentHashMap<String, AtomicLong>()
  val peerStarvationRecoveryFirstValidByPeer = ConcurrentHashMap<String, AtomicLong>()
  val peerStarvationRecoverySuccessByPeer = ConcurrentHashMap<String, AtomicLong>()
  val peerStarvationRecoveryFailureByPeer = ConcurrentHashMap<String, AtomicLong>()
  val peerLastStarvationRecoveryGeneration = ConcurrentHashMap<String, Long>()
  val peerLastStarvationRecoveryLatencyMs = ConcurrentHashMap<String, Long>()
  val validationStarvationBaselineByPeer = ConcurrentHashMap<String, PeerStarvationCounterSnapshot>()
  val addressRebindCountByIdentity = ConcurrentHashMap<String, AtomicLong>()
  val lastRebindWallMsByIdentity = ConcurrentHashMap<String, Long>()
  val rebindEvents = ConcurrentLinkedDeque<RebindEvent>()

  val totalScanResults = AtomicLong(0)
  val bodyFinderScanResults = AtomicLong(0)
  val malformedBodyFinderPayloads = AtomicLong(0)
  val selfScanResultsIgnored = AtomicLong(0)
  val invalidRssiTotalCount = AtomicLong(0)
  val advertiseRestartCount = AtomicLong(0)
  val scanRestartCount = AtomicLong(0)
  val txPackets = AtomicLong(0)
  val rxPackets = AtomicLong(0)
  val rxProtocolV2Packets = AtomicLong(0)
  val rxSameSessionPackets = AtomicLong(0)
  val peerExpireCount = AtomicLong(0)
  @Volatile var lastAnyScanResultWallMs: Long? = null
  @Volatile var lastBodyFinderScanResultWallMs: Long? = null
  @Volatile var lastValidBodyFinderRssiWallMs: Long? = null

  fun totalRebinds(): Long = addressRebindCountByIdentity.values.sumOf { it.get() }

  fun resetDiagnostics() {
    bleDetail = "BLE not started"
    bleScanState = "IDLE"
    bleAdvertiseState = "IDLE"
    bleScanMode = "NONE"
    bleScanFailureCode = null
    bleAdvertiseFailureCode = null
    bleAdvertiseStartedWallMs = null
    bleScanStartedWallMs = null
    socketState = "IDLE"
    multicastJoinState = "IDLE"
    totalScanResults.set(0)
    bodyFinderScanResults.set(0)
    malformedBodyFinderPayloads.set(0)
    selfScanResultsIgnored.set(0)
    invalidRssiTotalCount.set(0)
    advertiseRestartCount.set(0)
    scanRestartCount.set(0)
    txPackets.set(0)
    rxPackets.set(0)
    rxProtocolV2Packets.set(0)
    rxSameSessionPackets.set(0)
    peerExpireCount.set(0)
    lastAnyScanResultWallMs = null
    lastBodyFinderScanResultWallMs = null
    lastValidBodyFinderRssiWallMs = null
    lastScanRestartWallMs = 0
    scanGeneration.set(0)
    ValidationEventLog.reset()
    BleAcquisitionPolicy.reset(System.currentTimeMillis())
    peerPacketCounts.clear()
    peerLastSeenWallMs.clear()
    peerLastSeenMonotonicNs.clear()
    peerStaleSinceWallMs.clear()
    bleLastSeenWallMsByIdentity.clear()
    bleSeenCountByIdentity.clear()
    acquisitionStatsByIdentity.clear()
    validationAcquisitionBaselineByIdentity.clear()
    peerHealthStateByPeer.clear()
    starvationCandidateSinceByPeer.clear()
    starvationSinceByPeer.clear()
    peerStarvationCountByPeer.clear()
    peerStarvationRecoveryParticipationByPeer.clear()
    peerStarvationRecoveryFirstValidByPeer.clear()
    peerStarvationRecoverySuccessByPeer.clear()
    peerStarvationRecoveryFailureByPeer.clear()
    peerLastStarvationRecoveryGeneration.clear()
    peerLastStarvationRecoveryLatencyMs.clear()
    validationStarvationBaselineByPeer.clear()
    invalidRssiEventsByIdentity.clear()
    invalidRssiCountByIdentity.clear()
    lastValidRssiWallMsByIdentity.clear()
    lastInvalidRssiWallMsByIdentity.clear()
    lastInvalidRssiValueByIdentity.clear()
    lastValidRangeByPeer.clear()
    addressRebindCountByIdentity.clear()
    lastRebindWallMsByIdentity.clear()
    rebindEvents.clear()
  }

  fun snapshotAcquisitionForValidation() {
    validationAcquisitionBaselineByIdentity.clear()
    acquisitionStatsByIdentity.forEach { (identity, stats) ->
      validationAcquisitionBaselineByIdentity[identity] = stats.snapshot()
    }
    validationStarvationBaselineByPeer.clear()
    peers.keys.forEach { peerId ->
      validationStarvationBaselineByPeer[peerId] = PeerStarvationCounterSnapshot(
        peerStarvationCountByPeer[peerId]?.get() ?: 0,
        peerStarvationRecoveryParticipationByPeer[peerId]?.get() ?: 0,
        peerStarvationRecoveryFirstValidByPeer[peerId]?.get() ?: 0,
        peerStarvationRecoverySuccessByPeer[peerId]?.get() ?: 0,
        peerStarvationRecoveryFailureByPeer[peerId]?.get() ?: 0,
      )
    }
  }

  fun stopBle() {
    try { advertiseCallback?.let { advertiser?.stopAdvertising(it) } } catch (_: Throwable) {}
    try { scanCallback?.let { scanner?.stopScan(it) } } catch (_: Throwable) {}
    if (Build.VERSION.SDK_INT >= 36) {
      try { SystemRangingApi36.stop() } catch (_: Throwable) {}
    }
    advertiser = null
    scanner = null
    advertiseCallback = null
    scanCallback = null
    bleScanning = false
    bleAdvertising = false
    bleScanState = "IDLE"
    bleAdvertiseState = "IDLE"
    rssiWindows.clear()
    invalidRssiEventsByIdentity.clear()
    lastValidRangeByPeer.clear()
    bleAddressByIdentity.clear()
  }

  fun stop() {
    running = false
    try { socket?.close() } catch (_: Throwable) {}
    socket = null
    socketState = "CLOSED"
    peers.clear()
    publishedGeometryJson = null
    controlPlaneJson = null
    stopBle()
  }
}

class BodyFinderNativeModule : Module() {
  companion object { init { System.loadLibrary("body_finder_science") } }
  private external fun nativeEvaluateHumanPresence(inputJson: String): String

  override fun definition() = ModuleDefinition {
    Name("BodyFinderNative")

    Function("evaluateHumanPresenceJson") { inputJson: String ->
      nativeEvaluateHumanPresence(inputJson)
    }

    Function("sha256Text") { text: String ->
      MessageDigest.getInstance("SHA-256").digest(text.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
    }

    Function("shareJsonFile") { json: String, requestedFilename: String ->
      val ctx = appContext.reactContext ?: return@Function false
      val safeFilename = requestedFilename
        .replace(Regex("[^A-Za-z0-9._-]"), "_")
        .take(160)
        .let { if (it.endsWith(".json")) it else "$it.json" }
      val exportDir = File(ctx.cacheDir, "bodyfinder_exports").apply { mkdirs() }
      val file = File(exportDir, safeFilename)
      file.writeText(json, Charsets.UTF_8)
      val uri = FileProvider.getUriForFile(ctx, "${ctx.packageName}.bodyfinder.fileprovider", file)
      val sendIntent = Intent(Intent.ACTION_SEND).apply {
        type = "application/json"
        putExtra(Intent.EXTRA_STREAM, uri)
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        clipData = ClipData.newRawUri(safeFilename, uri)
      }
      val chooser = Intent.createChooser(sendIntent, "Body Finder JSON").apply {
        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
      }
      ctx.startActivity(chooser)
      true
    }
    Function("getCapabilitiesJson") {
      val ctx = appContext.reactContext ?: return@Function "{}"
      deviceReport(ctx).toString()
    }
    Function("getDiagnosticsJson") {
      val ctx = appContext.reactContext ?: return@Function "{}"
      diagnostics(ctx).toString()
    }
    Function("exportPreRunDiagnosticJson") { contextJson: String ->
      val ctx=appContext.reactContext?:return@Function "{}";val supplied=try{JSONObject(contextJson)}catch(_:Throwable){JSONObject()};val beforeRun=ValidationRuntime.runId;val beforeEnded=ValidationRuntime.endedWallMs
      supplied.put("evidence_class","PRE_RUN_DIAGNOSTIC_V1").put("acceptance_eligible",false).put("run_started",beforeRun!=null&&beforeEnded==null).put("report_version",33).put("snapshot_schema_version",16).put("wire_transport_telemetry",WireTransportV10.telemetry()).put("native_diagnostics",diagnostics(ctx))
      supplied.put("diagnostic_read_only",beforeRun==ValidationRuntime.runId&&beforeEnded==ValidationRuntime.endedWallMs).toString(2)
    }
    Function("getWifiRssi") {
      val ctx = appContext.reactContext ?: return@Function null
      wifiRssi(ctx)
    }
    Function("updateLocalState") { baseline: Double?, sigma: Double?, scanning: Boolean ->
      FabricRuntime.baseline = baseline
      FabricRuntime.sigma = sigma
      FabricRuntime.scanning = scanning
      true
    }
    Function("updateControlPlaneJson") { controlPlaneJson: String? ->
      FabricRuntime.controlPlaneJson = if (!controlPlaneJson.isNullOrBlank()) {
        try { JSONObject(controlPlaneJson).toString() } catch (_: Throwable) { null }
      } else null
      true
    }
    Function("updatePublishedGeometry") { publish: Boolean, geometryJson: String? ->
      FabricRuntime.publishedGeometryJson = if (publish && !geometryJson.isNullOrBlank()) {
        try { JSONObject(geometryJson).toString() } catch (_: Throwable) { null }
      } else null
      true
    }
    Function("updateGeometryState") { geometryState: String ->
      ValidationRuntime.updateGeometry(geometryState)
      true
    }
    Function("updateValidationTruthJson") { truthJson: String ->
      ValidationRuntime.updateTruth(truthJson)
      true
    }
    Function("updateAppVisibility") { visibility: String ->
      val now = System.currentTimeMillis()
      ValidationRuntime.appVisibility = visibility
      EnvironmentViolationTracker.noteVisibility(now, visibility)
      true
    }
    Function("startValidationRun") { scenario: String ->
      if (scenario.isBlank() || scenario == "UNSPECIFIED") return@Function "VALIDATION_ENVIRONMENT_INVALID:SCENARIO_REQUIRED"
            val ctx = appContext.reactContext ?: return@Function "VALIDATION_ENVIRONMENT_INVALID:NO_CONTEXT"
      var now = System.currentTimeMillis()
      val previousStrategy = BleAcquisitionPolicy.currentStrategy()
      var sessionBoundaryReset = false
      val previousRunCompleted = ValidationRuntime.runId != null && ValidationRuntime.endedWallMs != null
      if (previousRunCompleted && physicalValidationIssues(ctx).isEmpty() &&
          (previousStrategy == BleAcquisitionStrategy.FAILED_SAFE || previousStrategy == BleAcquisitionStrategy.COOLDOWN)) {
        sessionBoundaryReset = BleAcquisitionPolicy.prepareValidationRunBoundary(now)
      }
      now = System.currentTimeMillis()
      val preflight = validationPreflight(ctx, now)
        .put("session_boundary_reset", sessionBoundaryReset)
        .put("session_boundary_previous_strategy", previousStrategy.name)
        .put("recovery_budget_preserved_across_boundary", true)
      val blocking = preflight.optJSONArray("blocking_reasons") ?: JSONArray()
      if (blocking.length() > 0) {
        val reasons = (0 until blocking.length()).map { blocking.optString(it) }
        return@Function "VALIDATION_ENVIRONMENT_INVALID:${reasons.joinToString(",")}"
      }
      FabricRuntime.snapshotAcquisitionForValidation()
      val id = ValidationRuntime.start(
        now,
        FabricRuntime.peerExpireCount.get(),
        FabricRuntime.totalRebinds(),
        FabricRuntime.scanRestartCount.get(),
        FabricRuntime.txPackets.get(),
        FabricRuntime.rxPackets.get(),
        preflight.toString(),
        scenario,
      )
      setValidationKeepAwake(true)
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
      if(ValidationRuntime.requiresDistributedCommit()&&!ValidationRuntime.freezeCommitted())return@Function false
      val ctx = appContext.reactContext ?: return@Function false
      val now=System.currentTimeMillis()
      ValidationRuntime.end(now,FabricRuntime.peerExpireCount.get(),FabricRuntime.totalRebinds(),FabricRuntime.scanRestartCount.get(),FabricRuntime.txPackets.get(),FabricRuntime.rxPackets.get(),acquisitionProvenance(now),peerBleDiagnostics(now),if(Build.VERSION.SDK_INT>=36) SystemRangingApi36.diagnostics(now) else JSONObject().put("state","UNSUPPORTED"))
      setValidationKeepAwake(false)
      true
    }
    Function("getValidationRunJson") {
      val ctx = appContext.reactContext ?: return@Function "{}"
      validationRunDiagnostics(ctx).toString()
    }
    Function("getCompletedValidationRunsSummaryJson") {
      ValidationRuntime.completedRunsSummary().toString()
    }
    Function("selectValidationRun") { selectedRunId: String ->
      ValidationRuntime.selectRun(selectedRunId)
    }
    Function("getCalibrationSnapshotJson") {
      calibrationSnapshot().toString()
    }
    AsyncFunction("startFabric") { nodeId: String?, displayName: String?, sessionId: String? ->
      val ctx = appContext.reactContext ?: return@AsyncFunction false
      FabricRuntime.stop()
      FabricRuntime.resetDiagnostics()
      val prefs = ctx.getSharedPreferences("body-finder-runtime", Context.MODE_PRIVATE)
      val saved = prefs.getString("node-id-v2", null)
      val chosen = nodeId?.takeIf { it.isNotBlank() }
        ?: saved
        ?: UUID.randomUUID().toString().also {
          prefs.edit().putString("node-id-v2", it).apply()
        }
      FabricRuntime.nodeId = chosen
      FabricRuntime.instanceEpoch = UUID.randomUUID().toString()
      FabricRuntime.displayName = displayName?.takeIf { it.isNotBlank() } ?: (Build.MODEL ?: "Android")
      FabricRuntime.sessionId = sessionId?.takeIf { it.isNotBlank() } ?: "body-finder-lab"
      FabricRuntime.running = true
      startFieldService(ctx.applicationContext)
      startBle(ctx.applicationContext)
      startNetworkThread(ctx.applicationContext)
      true
    }
    Function("stopFabric") {
      val ctx = appContext.reactContext
      setValidationKeepAwake(false)
      if (ctx != null) stopFieldService(ctx.applicationContext)
      FabricRuntime.stop()
      true
    }
    Function("getPeersJson") {
      val ctx = appContext.reactContext
      if (ctx != null) expirePeers(ctx.applicationContext, System.currentTimeMillis())
      val arr = JSONArray()
      FabricRuntime.peers.values.forEach { pair ->
        try { val nowMono=SystemClock.elapsedRealtimeNanos();val nowWall=System.currentTimeMillis();val d=JSONObject(pair.first);val leaseAge=kotlin.math.max(0L,nowWall-pair.second);d.put("membership_lease_age_ms",leaseAge).put("membership_lease_state",if(leaseAge<=15_000L)"LIVE" else "EXPIRED");val rs=d.optJSONArray("ranges")?:JSONArray();for(i in 0 until rs.length()){val r=rs.optJSONObject(i)?:continue;val received=r.optLong("received_local_monotonic_ns",0L);val base=r.optLong("sender_range_age_ms",0L);if(received>0L)r.put("effective_age_ms",base+kotlin.math.max(0L,(nowMono-received)/1_000_000L))};arr.put(d) } catch (_: Throwable) {}
      }
      arr.toString()
    }
    Function("getLocalAdvertisementJson") {
      val ctx = appContext.reactContext ?: return@Function "{}"
      advertisement(ctx).toString()
    }
  }

  private fun setValidationKeepAwake(enabled: Boolean) {
    val activity = appContext.currentActivity ?: return
    activity.runOnUiThread {
      if (enabled) activity.window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
      else activity.window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    }
  }

  private fun probe(state: String, detail: String) = JSONObject().put("state", state).put("detail", detail)
  private fun hasPermission(ctx: Context, permission: String) =
    Build.VERSION.SDK_INT < 23 || ctx.checkSelfPermission(permission) == PackageManager.PERMISSION_GRANTED
  private fun state(ok: Boolean, detail: String) = probe(if (ok) "WORKING" else "UNSUPPORTED", detail)
  private fun ageMs(now: Long, then: Long?): Any = if (then == null) JSONObject.NULL else max(0L, now - then)

  private fun legacyBluetoothPermissionsGranted(ctx: Context): Boolean {
    if (Build.VERSION.SDK_INT >= 31) return true
    return hasPermission(ctx, Manifest.permission.BLUETOOTH) &&
      hasPermission(ctx, Manifest.permission.BLUETOOTH_ADMIN) &&
      hasPermission(ctx, Manifest.permission.ACCESS_FINE_LOCATION)
  }

  private fun modernBluetoothPermissionsGranted(ctx: Context): Boolean {
    if (Build.VERSION.SDK_INT < 31) return true
    return hasPermission(ctx, Manifest.permission.BLUETOOTH_SCAN) &&
      hasPermission(ctx, Manifest.permission.BLUETOOTH_ADVERTISE) &&
      hasPermission(ctx, Manifest.permission.BLUETOOTH_CONNECT)
  }

  private fun bluetoothPermissionsGranted(ctx: Context) =
    legacyBluetoothPermissionsGranted(ctx) && modernBluetoothPermissionsGranted(ctx)

  private fun locationServiceEnabled(ctx: Context): Boolean? {
    if (Build.VERSION.SDK_INT >= 31) return null
    return try {
      val manager = ctx.getSystemService(Context.LOCATION_SERVICE) as? LocationManager ?: return false
      if (Build.VERSION.SDK_INT >= 28) manager.isLocationEnabled else true
    } catch (_: Throwable) { null }
  }

  private fun physicalValidationIssues(ctx: Context): List<String> {
    val issues = mutableListOf<String>()
    val power = ctx.getSystemService(Context.POWER_SERVICE) as? PowerManager
    if (power?.isPowerSaveMode == true) issues += "BATTERY_SAVER_ON"
    if (power != null && !power.isInteractive) issues += "SCREEN_OFF"
    if (ValidationRuntime.appVisibility != "active") issues += "APP_NOT_FOREGROUND"
    if (FieldServiceState.state != "RUNNING") issues += "FIELD_SERVICE_NOT_RUNNING"
    val manager = ctx.getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager
    if (manager?.adapter?.isEnabled != true) issues += "BLUETOOTH_OFF"
    if (!bluetoothPermissionsGranted(ctx)) issues += "BLE_PERMISSIONS_MISSING"
    if (Build.VERSION.SDK_INT < 31 && locationServiceEnabled(ctx) == false) issues += "LOCATION_OFF"
    val expectedNow = expectedKnownPeerCount()
    val requiredExpected = if (ValidationRuntime.runId != null && ValidationRuntime.endedWallMs == null) ValidationRuntime.frozenExpectedPeerCount().coerceAtLeast(2) else 2
    if (expectedNow < requiredExpected) issues += "EXPECTED_BLE_PEER_COHORT_LOSS"
    if (!FabricRuntime.bleScanning) issues += "BLE_SCANNER_NOT_RUNNING"
    return issues.distinct()
  }

  private fun strategyFilterMode(strategy: BleAcquisitionStrategy): Pair<String, Int> =
    if (strategy == BleAcquisitionStrategy.UNFILTERED_RECOVERY) "UNFILTERED" to 0 else "MANUFACTURER_FILTERED" to 1

  private fun strategyEnvironmentDecision(now: Long = System.currentTimeMillis()): StrategyEnvironmentDecision {
    val strategy = BleAcquisitionPolicy.currentStrategy()
    val (mode, count) = strategyFilterMode(strategy)
    return EnvironmentStrategyValidator.evaluate(
      RecoveryAuthorizationContext(
        strategy = strategy,
        activeRecoveryGeneration = BleAcquisitionPolicy.activeRecoveryGeneration(),
        strategyRecoveryGeneration = BleAcquisitionPolicy.strategyRecoveryGeneration(),
        triggerKind = BleAcquisitionPolicy.activeRecoveryTriggerKind(),
        triggerPeerId = BleAcquisitionPolicy.activeRecoveryTriggerPeerId(),
        recoveryStartedWallMs = BleAcquisitionPolicy.recoveryStartedMs(),
        strategySinceWallMs = BleAcquisitionPolicy.strategySinceMs(),
        nowWallMs = now,
        filterMode = mode,
        hardwareFilterCount = count,
      )
    )
  }

  private fun validationEnvironmentIssues(ctx: Context, now: Long = System.currentTimeMillis()): Pair<List<String>, StrategyEnvironmentDecision> {
    val decision = strategyEnvironmentDecision(now)
    val issues = physicalValidationIssues(ctx).toMutableList()
    if (!decision.valid) issues += (decision.violationType ?: "UNAUTHORIZED_ACQUISITION_STRATEGY")
    return issues.distinct() to decision
  }

  private fun validationPreflight(ctx: Context, now: Long = System.currentTimeMillis()): JSONObject {
    val strategy = BleAcquisitionPolicy.currentStrategy()
    val (filterMode, hardwareFilterCount) = strategyFilterMode(strategy)
    val blocking = physicalValidationIssues(ctx).toMutableList()
    if (strategy != BleAcquisitionStrategy.FILTERED_PRIMARY) blocking += "START_REQUIRES_FILTERED_PRIMARY"
    if (filterMode != "MANUFACTURER_FILTERED" || hardwareFilterCount <= 0) blocking += "START_REQUIRES_HARDWARE_FILTER"
    val locationApplicable = Build.VERSION.SDK_INT < 31
    return JSONObject()
      .put("ready", blocking.isEmpty())
      .put("wall_ms", now)
      .put("captured_wall_ms", now)
      .put("bluetooth_on", (ctx.getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager)?.adapter?.isEnabled == true)
      .put("ble_permissions_ready", bluetoothPermissionsGranted(ctx))
      .put("battery_saver_off", (ctx.getSystemService(Context.POWER_SERVICE) as? PowerManager)?.isPowerSaveMode != true)
      .put("screen_on", (ctx.getSystemService(Context.POWER_SERVICE) as? PowerManager)?.isInteractive == true)
      .put("app_foreground", ValidationRuntime.appVisibility == "active")
      .put("foreground_service_running", FieldServiceState.state == "RUNNING")
      .put("ble_scanner_running", FabricRuntime.bleScanning)
      .put("expected_ble_peer_count", expectedKnownPeerCount())
      .put("expected_ble_peers", expectedKnownPeerCount())
      .put("expected_ble_peer_ids", JSONArray(FabricRuntime.peers.keys.toList().sorted()))
      .put("expected_ble_peers_ready", expectedKnownPeerCount() >= 2)
      .put("acquisition_strategy", strategy.name)
      .put("filter_mode", filterMode)
      .put("hardware_filter_count", hardwareFilterCount)
      .put("location_requirement_applicable", locationApplicable)
      .put("location_service_enabled", if (locationApplicable) (locationServiceEnabled(ctx) ?: JSONObject.NULL) else JSONObject.NULL)
      .put("blocking_reasons", JSONArray(blocking.distinct()))
      .put("issues", JSONArray(blocking.distinct()))
      .put("acceptance_minimum_ms", 330_000L)
      .put("recommended_long_run_ms", 330_000L)
  }

  private fun deviceReport(ctx: Context) = JSONObject().apply {
    put("platform", "android")
    put("manufacturer", Build.MANUFACTURER ?: "unknown")
    put("model", Build.MODEL ?: "unknown")
    put("android_api", Build.VERSION.SDK_INT)
    put("capabilities", capabilityMap(ctx))
  }

  private fun validSamples(identity: String, now: Long, windowMs: Long): List<RssiSample> =
    FabricRuntime.rssiWindows[identity]?.filter { now - it.ms <= windowMs } ?: emptyList()

  private fun invalidEvents(identity: String, now: Long, windowMs: Long): List<InvalidRssiEvent> =
    FabricRuntime.invalidRssiEventsByIdentity[identity]?.filter { now - it.ms <= windowMs } ?: emptyList()

  private fun fallbackEvidenceReadyCount(now: Long = System.currentTimeMillis()): Int {
    return FabricRuntime.peers.values.count { pair ->
      try {
        val peer = JSONObject(pair.first)
        val identity = peer.optString("ble_identity").takeIf { it.isNotBlank() && it != "null" } ?: return@count false
        validSamples(identity, now, RANGE_FRESHNESS_MS).size >= MIN_SAMPLES_FOR_RANGE
      } catch (_: Throwable) { false }
    }
  }

  private fun freshMetricReadyCount(now: Long = System.currentTimeMillis()): Int {
    var count = 0
    FabricRuntime.peers.values.forEach { pair ->
      try {
        val peer = JSONObject(pair.first)
        val peerId = peer.optString("node_id")
        val system = if (Build.VERSION.SDK_INT >= 36) SystemRangingApi36.measurements[peerId] else null
        if (system != null && system.distanceM != null && now - system.receivedWallMs <= RANGE_FRESHNESS_MS) {
          count++
          return@forEach
        }
        val estimate = fallbackEstimate(peer, now)
        if (estimate?.metricValid == true) count++
      } catch (_: Throwable) {}
    }
    return count
  }

  private fun metricReadyCount(now: Long = System.currentTimeMillis()): Int {
    var count = 0
    FabricRuntime.peers.values.forEach { pair ->
      try {
        val peer = JSONObject(pair.first)
        val peerId = peer.optString("node_id")
        val system = if (Build.VERSION.SDK_INT >= 36) SystemRangingApi36.measurements[peerId] else null
        if (system != null && system.distanceM != null && now - system.receivedWallMs <= RANGE_FRESHNESS_MS) {
          count++
          return@forEach
        }
        val estimate = fallbackEstimate(peer, now)
        if (estimate?.metricValid == true) {
          count++
          return@forEach
        }
        if (estimate?.status == BleRangeStatus.OUT_OF_DOMAIN_LOW || estimate?.status == BleRangeStatus.OUT_OF_DOMAIN_HIGH) return@forEach
        val cached = FabricRuntime.lastValidRangeByPeer[peerId]
        if (cached != null && BleContinuityPolicy.holdoverEligible(now - cached.estimateWallMs)) count++
      } catch (_: Throwable) {}
    }
    return count
  }

  private fun capabilityMap(ctx: Context): JSONObject {
    val pm = ctx.packageManager
    val wifi = ctx.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
    val bleFeature = pm.hasSystemFeature(PackageManager.FEATURE_BLUETOOTH_LE)
    val blePerm = bluetoothPermissionsGranted(ctx)
    val evidenceCount = fallbackEvidenceReadyCount()
    val metricCount = metricReadyCount()
    val bodyFinderSeen = FabricRuntime.bodyFinderScanResults.get() > 0
    return JSONObject().apply {
      put("wifi", state(wifi != null && wifi.isWifiEnabled, "Wi-Fi manager enabled"))
      put("wifi_rssi", state(wifiRssi(ctx) != null, "live connected-link RSSI; human-presence evidence only, never inter-node distance"))
      put("wifi_rtt", if (Build.VERSION.SDK_INT >= 28 && pm.hasSystemFeature(PackageManager.FEATURE_WIFI_RTT)) {
        probe("SUPPORTED_UNVERIFIED", "Wi-Fi RTT feature present; peer/AP ranging is not claimed until a live session reports measurements")
      } else state(false, "Wi-Fi RTT feature absent"))
      put("android_ranging_api", androidRangingProbe(ctx))
      put("ble", when {
        !bleFeature -> state(false, "BLE feature absent")
        !blePerm -> probe("PERMISSION_REQUIRED", "Bluetooth permissions required for this Android API level")
        Build.VERSION.SDK_INT < 31 && locationServiceEnabled(ctx) == false -> probe("PERMISSION_REQUIRED", "Location service must be enabled for reliable BLE scan on Android <= 11")
        else -> probe("WORKING", "BLE hardware and permissions available")
      })
      put("ble_peer_ranging", when {
        !bleFeature -> probe("UNSUPPORTED", "BLE feature absent")
        !blePerm -> probe("PERMISSION_REQUIRED", "Bluetooth permissions required")
        metricCount > 0 -> probe("WORKING_DEGRADED", "LIVE_METRIC_RANGE: $metricCount peer(s) have a fresh or bounded-holdover metric range; temporal provenance is exported")
        evidenceCount > 0 -> probe("WORKING_DEGRADED", "PROXIMITY_ONLY: fresh Body Finder BLE RSSI evidence exists but no usable metric range is currently available")
        Build.VERSION.SDK_INT >= 36 && SystemRangingApi36.hasFreshResult() -> probe("WORKING_DEGRADED", SystemRangingApi36.detail + "; fresh Android system ranging result available")
        bodyFinderSeen -> probe("WORKING_DEGRADED", "ACQUIRING: Body Finder BLE advertisement seen; waiting for enough fresh valid per-peer RSSI samples")
        FabricRuntime.bleScanning -> probe("SUPPORTED_UNVERIFIED", "ACQUIRING: BLE scan active but no Body Finder peer advertisement has been recognized yet")
        else -> probe("SUPPORTED_UNVERIFIED", FabricRuntime.bleDetail)
      })
      put("ble_range_calibration", probe(
        if (BleRangeEstimator.profile.validated) "WORKING_DEGRADED" else "SUPPORTED_UNVERIFIED",
        "profile=${BleRangeEstimator.profile.profileId}; validated=${BleRangeEstimator.profile.validated}; silent metric clamp disabled; bounded holdover=${BleContinuityPolicy.HOLDOVER_MAX_MS}ms"
      ))
      put("field_session_service", probe(
        if (FieldServiceState.state == "RUNNING") "WORKING" else "SUPPORTED_UNVERIFIED",
        "foreground service=${FieldServiceState.state}; screen-off/background behavior must be validated physically"
      ))
      put("imu", state(pm.hasSystemFeature(PackageManager.FEATURE_SENSOR_ACCELEROMETER), "accelerometer feature"))
      put("automatic_geometry_compute", probe("WORKING", "protocol-v2 automatic geometry solver runs in the app"))
      put("geometry_publication", probe("WORKING", "elected coordinator attaches its derived GeometrySolution revision to protocol-v2 advertisements"))
      put("csi", probe("UNSUPPORTED", "No public/verified CSI adapter loaded; RSSI is never labeled CSI"))
      put("udp_fabric", probe(if (FabricRuntime.socketState == "BOUND") "WORKING_DEGRADED" else "SUPPORTED_UNVERIFIED", "local UDP multicast/broadcast; socket=${FabricRuntime.socketState}; multicast=${FabricRuntime.multicastJoinState}"))
      put("compute", probe("WORKING", "Android Body Finder application runtime"))
    }
  }

  private fun androidRangingProbe(ctx: Context): JSONObject {
    if (Build.VERSION.SDK_INT < 36) return probe("UNSUPPORTED", "android.ranging.RangingManager requires Android API 36+")
    if (!hasPermission(ctx, RANGE_PERMISSION)) return probe("PERMISSION_REQUIRED", "android.permission.RANGING is required")
    return try {
      val clazz = Class.forName("android.ranging.RangingManager")
      val method = Context::class.java.getMethod("getSystemService", Class::class.java)
      val service = method.invoke(ctx, clazz)
      when {
        service == null -> probe("UNSUPPORTED", "RangingManager service unavailable")
        SystemRangingApi36.hasFreshResult() -> probe("WORKING_DEGRADED", SystemRangingApi36.detail + "; live system ranging result observed")
        else -> probe("SUPPORTED_UNVERIFIED", SystemRangingApi36.detail + "; BLE RSSI evidence remains independent and available")
      }
    } catch (e: Throwable) {
      probe("PROBE_FAILED", "RangingManager probe failed: ${e.javaClass.simpleName}")
    }
  }

  @Suppress("DEPRECATION")
  private fun wifiRssi(ctx: Context): Double? = try {
    val wm = ctx.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
    if (!wm.isWifiEnabled) null
    else wm.connectionInfo?.rssi?.toDouble()?.takeIf { it in -126.0..0.0 }
  } catch (_: Throwable) { null }

  private fun bleIdentity(nodeId: String = FabricRuntime.nodeId): String {
    val bytes = MessageDigest.getInstance("SHA-256")
      .digest(nodeId.toByteArray(Charsets.UTF_8))
      .copyOfRange(0, 8)
    return bytes.joinToString("") { "%02x".format(it.toInt() and 0xff) }
  }

  private fun addressFingerprint(address: String): String {
    val bytes = MessageDigest.getInstance("SHA-256")
      .digest((FabricRuntime.sessionId + ":" + address.uppercase()).toByteArray(Charsets.UTF_8))
      .copyOfRange(0, 6)
    return "sha256:" + bytes.joinToString("") { "%02x".format(it.toInt() and 0xff) }
  }

  private fun blePayload(): ByteArray {
    val id = bleIdentity()
    val out = ByteArray(10)
    out[0] = 0x42
    out[1] = 0x46
    for (i in 0 until 8) out[i + 2] = id.substring(i * 2, i * 2 + 2).toInt(16).toByte()
    return out
  }

  private fun payloadIdentity(data: ByteArray?): String? {
    if (data == null || data.size < 10 || data[0] != 0x42.toByte() || data[1] != 0x46.toByte()) return null
    return data.copyOfRange(2, 10).joinToString("") { "%02x".format(it.toInt() and 0xff) }
  }

  private fun scanSettings(): ScanSettings = BleAcquisitionPolicy.scanSettings()

  private fun scanFilter(): ScanFilter = BleAcquisitionPolicy.manufacturerFilter(MANUFACTURER_ID)

  private fun startScanner(
    scanner: android.bluetooth.le.BluetoothLeScanner,
    callback: ScanCallback,
    strategy: BleAcquisitionStrategy = BleAcquisitionStrategy.FILTERED_PRIMARY,
    reason: String = "START",
  ) {
    val now = System.currentTimeMillis()
    FabricRuntime.scanGeneration.incrementAndGet()
    when (strategy) {
      BleAcquisitionStrategy.UNFILTERED_RECOVERY -> {
        BleAcquisitionPolicy.startUnfilteredRecoveryScan(scanner, callback)
        FabricRuntime.bleScanMode = "LOW_LATENCY"
        FabricRuntime.bleDetail = "Temporary ALL_MATCHES recovery scan; Body Finder payload validation remains in software"
      }
      else -> {
        BleAcquisitionPolicy.startFilteredScan(scanner, callback, MANUFACTURER_ID)
        FabricRuntime.bleScanMode = "LOW_LATENCY"
        FabricRuntime.bleDetail = "Manufacturer-filtered low-latency Body Finder scan active; strategy=${strategy.name}"
      }
    }
    BleAcquisitionPolicy.transition(strategy, now, reason)
    FabricRuntime.bleScanStartedWallMs = now
    FabricRuntime.bleScanning = true
    FabricRuntime.bleScanState = if (FabricRuntime.bodyFinderScanResults.get() > 0) "ACTIVE_PEER_SEEN" else "ACTIVE_NO_BODY_FINDER_PEER"
  }

  private fun globalScannerHealth(now: Long): GlobalBleScannerHealth {
    if (!FabricRuntime.bleScanning) return GlobalBleScannerHealth.GLOBAL_SCANNER_STOPPED
    if (FabricRuntime.bleScanFailureCode != null) return GlobalBleScannerHealth.GLOBAL_SCANNER_ERROR
    val anchor = FabricRuntime.lastAnyScanResultWallMs ?: FabricRuntime.bleScanStartedWallMs ?: return GlobalBleScannerHealth.GLOBAL_SCANNER_STARTING
    return if (now - anchor >= SCAN_STALL_RESTART_MS) GlobalBleScannerHealth.GLOBAL_SCANNER_STALLED else GlobalBleScannerHealth.GLOBAL_SCANNER_HEALTHY
  }

  private fun expectedKnownPeerCount(): Int = FabricRuntime.peers.values.count { pair ->
    try {
      val peer = JSONObject(pair.first)
      peer.optString("ble_identity").let { it.isNotBlank() && it != "null" }
    } catch (_: Throwable) { false }
  }

  private fun recentKnownPeerCount(now: Long): Int = FabricRuntime.peers.values.count { pair ->
    try {
      val peer = JSONObject(pair.first)
      val identity = peer.optString("ble_identity").takeIf { it.isNotBlank() && it != "null" } ?: return@count false
      val seen = FabricRuntime.bleLastSeenWallMsByIdentity[identity] ?: return@count false
      now - seen <= BleAcquisitionPolicy.COHORT_STALL_THRESHOLD_MS
    } catch (_: Throwable) { false }
  }

  private fun bodyFinderCohortHealth(now: Long): BodyFinderCohortHealth {
    if (!FabricRuntime.bleScanning) return BodyFinderCohortHealth.BF_COHORT_UNAVAILABLE
    val expected = expectedKnownPeerCount()
    if (expected <= 0) return BodyFinderCohortHealth.BF_COHORT_UNAVAILABLE
    val recent = recentKnownPeerCount(now)
    if (recent >= expected) return BodyFinderCohortHealth.BF_COHORT_HEALTHY
    if (recent > 0) return BodyFinderCohortHealth.BF_COHORT_SPARSE
    if (BleAcquisitionPolicy.currentStrategy() == BleAcquisitionStrategy.UNFILTERED_RECOVERY) return BodyFinderCohortHealth.BF_COHORT_RECOVERING
    val global = globalScannerHealth(now)
    val lastBf = FabricRuntime.lastBodyFinderScanResultWallMs ?: FabricRuntime.bleScanStartedWallMs ?: now
    return if (global == GlobalBleScannerHealth.GLOBAL_SCANNER_HEALTHY && now - lastBf > BleAcquisitionPolicy.COHORT_STALL_THRESHOLD_MS) {
      BodyFinderCohortHealth.BF_COHORT_STALLED
    } else BodyFinderCohortHealth.BF_COHORT_SPARSE
  }

  private fun peerIdentity(peerId: String): String? = FabricRuntime.peers[peerId]?.first?.let { raw ->
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
    val scanner = FabricRuntime.scanner ?: return false
    val callback = FabricRuntime.scanCallback ?: return false
    return try {
      scanner.stopScan(callback)
      try { Thread.sleep(BleAcquisitionPolicy.RECOVERY_QUIET_MS) } catch (_: InterruptedException) {}
      startScanner(scanner, callback, strategy, reason)
      FabricRuntime.scanRestartCount.incrementAndGet()
      FabricRuntime.lastScanRestartWallMs = now
      true
    } catch (e: Throwable) {
      FabricRuntime.bleDetail = "BLE adaptive recovery failed: ${e.javaClass.simpleName}: ${e.message}"
      false
    }
  }

  private fun maintainAdaptiveScanner(ctx: Context, now: Long) {
    val global = globalScannerHealth(now)
    var cohort = bodyFinderCohortHealth(now)
    BleAcquisitionPolicy.updateCohortHealth(cohort, now)

    // dev16: action targets use elapsedRealtime internally; wall_ms remains evidence only.
    if (BleAcquisitionPolicy.currentStrategy() == BleAcquisitionStrategy.UNFILTERED_RECOVERY &&
        (BleAcquisitionPolicy.recoveryUnfilteredElapsedMs() ?: 0L) >= BleAcquisitionPolicy.RECOVERY_UNFILTERED_ACTION_TARGET_MS) {
      val triggerPeer = BleAcquisitionPolicy.activeRecoveryTriggerPeerId()
      val triggerKind = BleAcquisitionPolicy.activeRecoveryTriggerKind()
      BleAcquisitionPolicy.noteRecoveryFailure(now)
      if (triggerPeer != null && triggerKind == RecoveryTriggerKind.PEER_STARVATION) {
        FabricRuntime.peerHealthStateByPeer[triggerPeer] = PeerHealthState.PEER_RECOVERY_FAILED.name
        FabricRuntime.peerStarvationRecoveryFailureByPeer.computeIfAbsent(triggerPeer) { AtomicLong(0) }.incrementAndGet()
      }
      restartScannerWithStrategy(now, BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE, "RECOVERY_ACTION_TARGET_EXPIRED")
      return
    }
    if (BleAcquisitionPolicy.currentStrategy() == BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE &&
        (BleAcquisitionPolicy.filteredProbeElapsedMs() ?: 0L) >= BleAcquisitionPolicy.FILTERED_PROBE_ACTION_TARGET_MS) {
      BleAcquisitionPolicy.transition(BleAcquisitionStrategy.FILTERED_PRIMARY, now, "PROBE_ACTION_TARGET")
      restartScannerWithStrategy(now, BleAcquisitionStrategy.FILTERED_PRIMARY, "PROBE_ACTION_TARGET")
      return
    }

    if (global == GlobalBleScannerHealth.GLOBAL_SCANNER_STALLED) {
      val current = BleAcquisitionPolicy.currentStrategy()
      if (current == BleAcquisitionStrategy.UNFILTERED_RECOVERY) {
        val started = BleAcquisitionPolicy.recoveryStartedMs() ?: now
        if (now - started >= BleAcquisitionPolicy.RECOVERY_UNFILTERED_WINDOW_MS) {
          BleAcquisitionPolicy.noteRecoveryFailure(now)
          restartScannerWithStrategy(now, BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE, "RECOVERY_WINDOW_EXPIRED_GLOBAL_STALL")
          return
        }
      }
      if (current == BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE &&
          now - BleAcquisitionPolicy.strategySinceMs() >= BleAcquisitionPolicy.FILTERED_PROBE_EXIT_TARGET_MS) {
        BleAcquisitionPolicy.transition(BleAcquisitionStrategy.FILTERED_PRIMARY, now, "PROBE_EXIT_TARGET_GLOBAL_STALL")
        restartScannerWithStrategy(now, BleAcquisitionStrategy.FILTERED_PRIMARY, "PROBE_EXIT_TARGET_GLOBAL_STALL")
        return
      }
      if (now - FabricRuntime.lastScanRestartWallMs >= BleAcquisitionPolicy.MIN_RESTART_COOLDOWN_MS) {
        restartScannerWithStrategy(now, current, "GLOBAL_SCANNER_STALLED")
      }
      return
    }

    when (BleAcquisitionPolicy.currentStrategy()) {
      BleAcquisitionStrategy.FILTERED_PRIMARY -> {
        if (cohort == BodyFinderCohortHealth.BF_COHORT_STALLED) {
          if (BleAcquisitionPolicy.canStartRecovery(now)) {
            BleAcquisitionPolicy.beginRecovery(now, "BF_COHORT_STALLED", RecoveryTriggerKind.FULL_COHORT_STALL)
            restartScannerWithStrategy(now, BleAcquisitionStrategy.UNFILTERED_RECOVERY, "BF_COHORT_STALLED")
          } else if(BleAcquisitionPolicy.recoveryAttemptsInWindow(now)>=BleAcquisitionPolicy.MAX_RECOVERY_ATTEMPTS_PER_5MIN) BleAcquisitionPolicy.markFailedSafe(now,"MAX_RECOVERY_ATTEMPTS")
        } else {
          val environmentAllowsRecovery = ValidationRuntime.runId == null || ValidationRuntime.endedWallMs != null || physicalValidationIssues(ctx).isEmpty()
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
      BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE -> {
        cohort = bodyFinderCohortHealth(now)
        if (now - BleAcquisitionPolicy.strategySinceMs() >= BleAcquisitionPolicy.FILTERED_PROBE_EXIT_TARGET_MS) {
          BleAcquisitionPolicy.transition(BleAcquisitionStrategy.FILTERED_PRIMARY, now, if (cohort == BodyFinderCohortHealth.BF_COHORT_STALLED) "PROBE_EXIT_TARGET_STALLED" else "PROBE_STABLE")
        }
      }
      BleAcquisitionStrategy.COOLDOWN -> {
        if (now - BleAcquisitionPolicy.strategySinceMs() >= BleAcquisitionPolicy.MIN_RESTART_COOLDOWN_MS) {
          BleAcquisitionPolicy.transition(BleAcquisitionStrategy.FILTERED_PRIMARY, now, "COOLDOWN_COMPLETE")
        }
      }
      BleAcquisitionStrategy.FAILED_SAFE -> if(BleAcquisitionPolicy.recoveryAttemptsInWindow(now)<BleAcquisitionPolicy.MAX_RECOVERY_ATTEMPTS_PER_5MIN && now-FabricRuntime.lastScanRestartWallMs>=BleAcquisitionPolicy.MIN_RESTART_COOLDOWN_MS) BleAcquisitionPolicy.transition(BleAcquisitionStrategy.FILTERED_PRIMARY,now,"FAILED_SAFE_WINDOW_CLEARED")
    }
  }

  private fun startBle(ctx: Context) {
    try {
      val manager = ctx.getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager ?: run {
        FabricRuntime.bleDetail = "BluetoothManager unavailable"
        FabricRuntime.bleScanState = "UNAVAILABLE"
        return
      }
      val adapter = manager.adapter ?: run {
        FabricRuntime.bleDetail = "Bluetooth adapter unavailable"
        FabricRuntime.bleScanState = "UNAVAILABLE"
        return
      }
      if (!adapter.isEnabled) {
        FabricRuntime.bleDetail = "Bluetooth disabled"
        FabricRuntime.bleScanState = "DISABLED"
        FabricRuntime.lastValidRangeByPeer.clear()
        return
      }
      if (!bluetoothPermissionsGranted(ctx)) {
        FabricRuntime.bleDetail = "Bluetooth permission required for API ${Build.VERSION.SDK_INT}"
        FabricRuntime.bleScanState = "PERMISSION_REQUIRED"
        return
      }
      if (Build.VERSION.SDK_INT < 31 && locationServiceEnabled(ctx) == false) {
        FabricRuntime.bleDetail = "Location service disabled; Android <=11 may suppress BLE scan results"
        FabricRuntime.bleScanState = "LOCATION_REQUIRED"
        return
      }
      val scanner = adapter.bluetoothLeScanner ?: run {
        FabricRuntime.bleDetail = "BLE scanner unavailable"
        FabricRuntime.bleScanState = "UNAVAILABLE"
        return
      }
      val advertiser = adapter.bluetoothLeAdvertiser
      FabricRuntime.scanner = scanner
      FabricRuntime.advertiser = advertiser
      FabricRuntime.bleScanState = "STARTING"

      val scanCb = object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult) { recordScan(result) }
        override fun onBatchScanResults(results: MutableList<ScanResult>) { results.forEach { recordScan(it) } }
        override fun onScanFailed(errorCode: Int) {
          FabricRuntime.bleScanning = false
          FabricRuntime.bleScanState = "FAILED"
          FabricRuntime.bleScanFailureCode = errorCode
          FabricRuntime.bleDetail = "BLE scan failed code=$errorCode"
        }
      }
      FabricRuntime.scanCallback = scanCb
      BleAcquisitionPolicy.reset(System.currentTimeMillis())
      startScanner(scanner, scanCb, BleAcquisitionStrategy.FILTERED_PRIMARY, "INITIAL_FILTERED_PRIMARY")

      if (advertiser != null) {
        FabricRuntime.bleAdvertiseState = "STARTING"
        val advCb = object : AdvertiseCallback() {
          override fun onStartSuccess(settingsInEffect: AdvertiseSettings) {
            FabricRuntime.bleAdvertising = true
            FabricRuntime.bleAdvertiseState = "ACTIVE"
            FabricRuntime.bleAdvertiseStartedWallMs = System.currentTimeMillis()
            FabricRuntime.bleDetail = "BLE scan + Body Finder advertisement active"
          }
          override fun onStartFailure(errorCode: Int) {
            FabricRuntime.bleAdvertising = false
            FabricRuntime.bleAdvertiseState = "FAILED"
            FabricRuntime.bleAdvertiseFailureCode = errorCode
            FabricRuntime.bleDetail = "BLE scan active; advertisement unavailable code=$errorCode"
          }
        }
        FabricRuntime.advertiseCallback = advCb
        val advertiseSettings = AdvertiseSettings.Builder()
          .setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_LATENCY)
          .setTxPowerLevel(AdvertiseSettings.ADVERTISE_TX_POWER_MEDIUM)
          .setConnectable(false)
          .build()
        val data = AdvertiseData.Builder()
          .addManufacturerData(MANUFACTURER_ID, blePayload())
          .setIncludeTxPowerLevel(true)
          .build()
        FabricRuntime.advertiseRestartCount.incrementAndGet()
        advertiser.startAdvertising(advertiseSettings, data, advCb)
      } else {
        FabricRuntime.bleAdvertiseState = "UNSUPPORTED"
        FabricRuntime.bleDetail = "BLE scan active; peripheral advertising unsupported on this device"
      }
    } catch (e: SecurityException) {
      FabricRuntime.bleScanState = "PERMISSION_REQUIRED"
      FabricRuntime.bleDetail = "BLE permission denied: ${e.message}"
    } catch (e: Throwable) {
      FabricRuntime.bleScanState = "FAILED"
      FabricRuntime.bleDetail = "BLE start failed: ${e.javaClass.simpleName}: ${e.message}"
    }
  }

  private fun trimValidQueue(queue: ConcurrentLinkedDeque<RssiSample>, now: Long) {
    while (queue.size > MAX_RSSI_SAMPLES) queue.pollFirst()
    while (true) {
      val first = queue.peekFirst() ?: break
      if (now - first.ms <= WINDOW_RETENTION_MS) break else queue.pollFirst()
    }
  }

  private fun trimInvalidQueue(queue: ConcurrentLinkedDeque<InvalidRssiEvent>, now: Long) {
    while (queue.size > MAX_INVALID_RSSI_EVENTS) queue.pollFirst()
    while (true) {
      val first = queue.peekFirst() ?: break
      if (now - first.ms <= WINDOW_RETENTION_MS) break else queue.pollFirst()
    }
  }

  private fun recordScan(result: ScanResult) {
    val now = System.currentTimeMillis()
    FabricRuntime.totalScanResults.incrementAndGet()
    FabricRuntime.lastAnyScanResultWallMs = now
    val raw = result.scanRecord?.getManufacturerSpecificData(MANUFACTURER_ID) ?: return
    val id = payloadIdentity(raw)
    if (id == null) {
      FabricRuntime.malformedBodyFinderPayloads.incrementAndGet()
      return
    }
    if (id == bleIdentity()) {
      FabricRuntime.selfScanResultsIgnored.incrementAndGet()
      return
    }
    FabricRuntime.bodyFinderScanResults.incrementAndGet()
        FabricRuntime.lastBodyFinderScanResultWallMs = now
    FabricRuntime.bleLastSeenWallMsByIdentity[id] = now
    FabricRuntime.bleSeenCountByIdentity.computeIfAbsent(id) { AtomicLong(0) }.incrementAndGet()
    FabricRuntime.bleScanState = "ACTIVE_PEER_SEEN"

    val validRssi = BleRangeEstimator.isValidBleRssi(result.rssi.toDouble())
    val callbackPeerId = peerIdForIdentity(id)
    val acquisitionStats = FabricRuntime.acquisitionStatsByIdentity.computeIfAbsent(id) { BleAcquisitionStats() }
    if (validRssi && BleAcquisitionPolicy.currentStrategy() == BleAcquisitionStrategy.UNFILTERED_RECOVERY) {
      val recoveryGeneration = BleAcquisitionPolicy.activeRecoveryGeneration()
      val acceptedFirstValid = BleAcquisitionPolicy.noteRecoveryFirstValidCallback(now, callbackPeerId)
      if (acceptedFirstValid && recoveryGeneration != null) {
        acquisitionStats.noteFirstValidRecovery(recoveryGeneration, now)
      }
      if (acceptedFirstValid && callbackPeerId != null && BleAcquisitionPolicy.activeRecoveryTriggerKind() == RecoveryTriggerKind.PEER_STARVATION) {
        FabricRuntime.peerStarvationRecoveryFirstValidByPeer.computeIfAbsent(callbackPeerId) { AtomicLong(0) }.incrementAndGet()
      }
    }
    acquisitionStats.record(now, validRssi, BleAcquisitionPolicy.currentStrategy())

    val advertisedTx = result.scanRecord?.txPowerLevel?.takeIf { it in -100..20 } ?: Int.MIN_VALUE
    if (validRssi) {
      val queue = FabricRuntime.rssiWindows.computeIfAbsent(id) { ConcurrentLinkedDeque() }
      queue.addLast(RssiSample(result.rssi, advertisedTx, now))
      FabricRuntime.lastValidRssiWallMsByIdentity[id] = now
      FabricRuntime.lastValidBodyFinderRssiWallMs = now
      trimValidQueue(queue, now)
      HumanEvidenceTimeline.recordBle(FabricRuntime.nodeId, id, result.rssi, advertisedTx, now)
    } else {
      FabricRuntime.invalidRssiTotalCount.incrementAndGet()
      FabricRuntime.invalidRssiCountByIdentity.computeIfAbsent(id) { AtomicLong(0) }.incrementAndGet()
      FabricRuntime.lastInvalidRssiWallMsByIdentity[id] = now
      FabricRuntime.lastInvalidRssiValueByIdentity[id] = result.rssi
      val invalidQueue = FabricRuntime.invalidRssiEventsByIdentity.computeIfAbsent(id) { ConcurrentLinkedDeque() }
      invalidQueue.addLast(InvalidRssiEvent(result.rssi, now))
      trimInvalidQueue(invalidQueue, now)
    }

    try {
      val address = result.device.address?.uppercase()
      if (!address.isNullOrBlank()) {
        val old = FabricRuntime.bleAddressByIdentity.put(id, address)
        if (old != null && old != address) {
          val lastRebind = FabricRuntime.lastRebindWallMsByIdentity[id] ?: 0L
          if (now - lastRebind >= 1_000L) {
            FabricRuntime.addressRebindCountByIdentity.computeIfAbsent(id) { AtomicLong(0) }.incrementAndGet()
            FabricRuntime.lastRebindWallMsByIdentity[id] = now
            FabricRuntime.rebindEvents.addLast(
              RebindEvent(
                identity = id,
                previousFingerprint = addressFingerprint(old),
                newFingerprint = addressFingerprint(address),
                wallMs = now,
                reason = "ADDRESS_CHANGED",
              )
            )
            while (FabricRuntime.rebindEvents.size > MAX_REBIND_EVENTS) FabricRuntime.rebindEvents.pollFirst()
          }
        }
      }
    } catch (_: SecurityException) {}
  }

  private fun desiredSystemRangingPeers(): List<SystemRangingApi36.Peer> {
    if (Build.VERSION.SDK_INT < 36) return emptyList()
    return FabricRuntime.peers.values.mapNotNull { pair ->
      try {
        val peer = JSONObject(pair.first)
        val peerId = peer.optString("node_id").takeIf { it.isNotBlank() } ?: return@mapNotNull null
        val identity = peer.optString("ble_identity").takeIf { it.isNotBlank() && it != "null" } ?: return@mapNotNull null
        val address = FabricRuntime.bleAddressByIdentity[identity] ?: return@mapNotNull null
        SystemRangingApi36.Peer(peerId, address)
      } catch (_: Throwable) { null }
    }
  }

  private fun fallbackEstimate(peer: JSONObject, now: Long): BleRangeEstimate? {
    val identity = peer.optString("ble_identity").takeIf { it.isNotBlank() && it != "null" } ?: return null
    val samples = validSamples(identity, now, RANGE_FRESHNESS_MS)
    val txValues = samples.mapNotNull { sample -> sample.txPower.takeIf { it != Int.MIN_VALUE }?.toDouble() }
    return BleRangeEstimator.estimate(
      samples.map { it.rssi.toDouble() },
      txValues,
      MIN_SAMPLES_FOR_RANGE,
    )
  }

  private fun buildBleObservation(
    peerId: String,
    distanceM: Double?,
    sigmaM: Double?,
    rawDistanceM: Double?,
    rssiDbm: Double?,
    metricValid: Boolean,
    rangeStatus: String,
    calibrationState: String,
    proximityBand: String?,
    detail: String,
    observationMonotonicNs: Long,
    temporalState: BleRangeTemporalState,
    rangeAgeMs: Long,
  ): JSONObject = JSONObject()
    .put("session_id", FabricRuntime.sessionId)
    .put("observer_node_id", FabricRuntime.nodeId)
    .put("peer_node_id", peerId)
    .put("technology", "BLE_RSSI")
    .put("monotonic_ns", observationMonotonicNs)
    .put("source_observation_monotonic_ns", observationMonotonicNs)
    .put("range_age_ms", rangeAgeMs)
    .put("range_temporal_state", temporalState.name)
    .put("distance_m", distanceM ?: JSONObject.NULL)
    .put("distance_sigma_m", sigmaM ?: JSONObject.NULL)
    .put("raw_distance_m", rawDistanceM ?: JSONObject.NULL)
    .put("azimuth_deg", JSONObject.NULL)
    .put("azimuth_sigma_deg", JSONObject.NULL)
    .put("elevation_deg", JSONObject.NULL)
    .put("elevation_sigma_deg", JSONObject.NULL)
    .put("rssi_dbm", rssiDbm ?: JSONObject.NULL)
    .put("quality", "LOW")
    .put("metric_valid", metricValid)
    .put("range_status", rangeStatus)
    .put("calibration_profile_id", BleRangeEstimator.profile.profileId)
    .put("calibration_state", calibrationState)
    .put("proximity_band", proximityBand ?: JSONObject.NULL)
    .put("source_detail", detail)

  private fun fallbackObservation(peer: JSONObject, now: Long, mono: Long): JSONObject? {
    val peerId = peer.optString("node_id").takeIf { it.isNotBlank() } ?: return null
    val identity = peer.optString("ble_identity").takeIf { it.isNotBlank() && it != "null" } ?: return null
    val estimate = fallbackEstimate(peer, now) ?: return null

    if (estimate.metricValid && estimate.distanceM != null && estimate.sigmaM != null) {
      FabricRuntime.lastValidRangeByPeer[peerId] = LastValidRangeState(
        peerNodeId = peerId,
        bleIdentity = identity,
        distanceM = estimate.distanceM,
        sigmaM = estimate.sigmaM,
        rawDistanceM = estimate.rawDistanceM,
        medianRssiDbm = estimate.medianRssiDbm,
        profileId = estimate.profileId,
        calibrationState = estimate.calibrationState,
        observationMonotonicNs = mono,
        estimateWallMs = now,
        sourceDetail = estimate.detail,
      )
      return buildBleObservation(
        peerId, estimate.distanceM, estimate.sigmaM, estimate.rawDistanceM, estimate.medianRssiDbm,
        true, estimate.status.name, estimate.calibrationState, estimate.proximityBand, estimate.detail,
        mono, BleRangeTemporalState.FRESH, 0L,
      )
    }

    if (estimate.status == BleRangeStatus.OUT_OF_DOMAIN_LOW || estimate.status == BleRangeStatus.OUT_OF_DOMAIN_HIGH) {
      FabricRuntime.lastValidRangeByPeer.remove(peerId)
      return buildBleObservation(
        peerId, null, null, estimate.rawDistanceM, estimate.medianRssiDbm,
        false, estimate.status.name, estimate.calibrationState, estimate.proximityBand, estimate.detail,
        mono, BleRangeTemporalState.OUT_OF_DOMAIN, 0L,
      )
    }

    if (estimate.status == BleRangeStatus.NONFINITE || estimate.status == BleRangeStatus.INVALID_RSSI) {
      FabricRuntime.lastValidRangeByPeer.remove(peerId)
      return buildBleObservation(
        peerId, null, null, estimate.rawDistanceM, estimate.medianRssiDbm,
        false, estimate.status.name, estimate.calibrationState, estimate.proximityBand, estimate.detail,
        mono, BleRangeTemporalState.INVALID, 0L,
      )
    }

    val cached = FabricRuntime.lastValidRangeByPeer[peerId]
    if (cached != null) {
      val age = max(0L, now - cached.estimateWallMs)
      if (BleContinuityPolicy.holdoverEligible(age)) {
        val agedSigma = BleContinuityPolicy.agedSigma(cached.sigmaM, age)
        return buildBleObservation(
          peerId,
          cached.distanceM,
          agedSigma,
          cached.rawDistanceM,
          cached.medianRssiDbm,
          true,
          BleRangeStatus.VALID_METRIC.name,
          cached.calibrationState,
          cached.medianRssiDbm?.let { if (it >= -60) "NEAR" else if (it >= -72) "MID" else if (it >= -84) "FAR" else "VERY_FAR" },
          "bounded BLE metric HOLDOVER; last_valid_age_ms=$age; sigma inflated ${"%.3f".format(cached.sigmaM)} -> ${"%.3f".format(agedSigma)}; original=${cached.sourceDetail}",
          cached.observationMonotonicNs,
          BleRangeTemporalState.HOLDOVER,
          age,
        )
      }
      FabricRuntime.lastValidRangeByPeer.remove(peerId)
    }

    if (estimate.status == BleRangeStatus.INSUFFICIENT_SAMPLES) return null
    return buildBleObservation(
      peerId, null, null, estimate.rawDistanceM, estimate.medianRssiDbm,
      false, estimate.status.name, estimate.calibrationState, estimate.proximityBand, estimate.detail,
      mono, BleRangeTemporalState.ACQUIRING, 0L,
    )
  }

  private fun rangeObservations(): JSONArray {
    val arr = JSONArray()
    val now = System.currentTimeMillis()
    val mono = SystemClock.elapsedRealtimeNanos()
    FabricRuntime.peers.values.forEach { pair ->
      try {
        val peer = JSONObject(pair.first)
        val peerId = peer.optString("node_id")
        if (Build.VERSION.SDK_INT >= 36) {
          val system = SystemRangingApi36.measurements[peerId]
          if (system != null && now - system.receivedWallMs <= RANGE_FRESHNESS_MS && system.distanceM != null) {
            arr.put(
              JSONObject()
                .put("session_id", FabricRuntime.sessionId)
                .put("observer_node_id", FabricRuntime.nodeId)
                .put("peer_node_id", peerId)
                .put("technology", system.technology)
                .put("monotonic_ns", system.monotonicNs)
                .put("source_observation_monotonic_ns", system.monotonicNs)
                .put("range_age_ms", max(0L, now - system.receivedWallMs))
                .put("range_temporal_state", BleRangeTemporalState.FRESH.name)
                .put("distance_m", system.distanceM)
                .put("distance_sigma_m", system.distanceSigmaM ?: max(1.5, system.distanceM * 0.75))
                .put("raw_distance_m", system.distanceM)
                .put("azimuth_deg", JSONObject.NULL)
                .put("azimuth_sigma_deg", JSONObject.NULL)
                .put("elevation_deg", JSONObject.NULL)
                .put("elevation_sigma_deg", JSONObject.NULL)
                .put("rssi_dbm", system.rssiDbm ?: JSONObject.NULL)
                .put("quality", system.quality)
                .put("metric_valid", true)
                .put("range_status", "VALID")
                .put("calibration_profile_id", JSONObject.NULL)
                .put("calibration_state", "SYSTEM_RANGE")
                .put("proximity_band", JSONObject.NULL)
                .put("source_detail", system.sourceDetail)
            )
            return@forEach
          }
        }
        fallbackObservation(peer, now, mono)?.let { arr.put(it) }
      } catch (_: Throwable) {}
    }
    return arr
  }

  private fun temporalStateForPeer(peerId: String, estimate: BleRangeEstimate?, now: Long): BleRangeTemporalState {
    val cached = FabricRuntime.lastValidRangeByPeer[peerId]
    val age = cached?.let { max(0L, now - it.estimateWallMs) }
    return BleContinuityPolicy.temporalState(
      currentMetricValid = estimate?.metricValid == true,
      explicitOutOfDomain = estimate?.status == BleRangeStatus.OUT_OF_DOMAIN_LOW || estimate?.status == BleRangeStatus.OUT_OF_DOMAIN_HIGH,
      explicitInvalid = estimate?.status == BleRangeStatus.NONFINITE || estimate?.status == BleRangeStatus.INVALID_RSSI,
      lastValidAgeMs = age,
    )
  }

  private fun peerBleDiagnostics(now: Long): JSONArray {
    val arr = JSONArray()
    FabricRuntime.peers.values.forEach { pair ->
      try {
        val peer = JSONObject(pair.first)
        val peerId = peer.optString("node_id")
        val identity = peer.optString("ble_identity").takeIf { it.isNotBlank() && it != "null" }
        val validFresh = identity?.let { validSamples(it, now, RANGE_FRESHNESS_MS) } ?: emptyList()
        val validRetained = identity?.let { validSamples(it, now, WINDOW_RETENTION_MS) } ?: emptyList()
        val invalidFresh = identity?.let { invalidEvents(it, now, RANGE_FRESHNESS_MS) } ?: emptyList()
        val invalidRetained = identity?.let { invalidEvents(it, now, WINDOW_RETENTION_MS) } ?: emptyList()
        val lastValidSample = validRetained.maxByOrNull { it.ms }
        val lastInvalidSample = invalidRetained.maxByOrNull { it.ms }
        val seenAt = identity?.let { FabricRuntime.bleLastSeenWallMsByIdentity[it] }
        val address = identity?.let { FabricRuntime.bleAddressByIdentity[it] }
        val estimate = if (identity != null) fallbackEstimate(peer, now) else null
        val temporalState = temporalStateForPeer(peerId, estimate, now)
        val cached = FabricRuntime.lastValidRangeByPeer[peerId]
        val cachedAge = cached?.let { max(0L, now - it.estimateWallMs) }
        val metricReady = temporalState == BleRangeTemporalState.FRESH || temporalState == BleRangeTemporalState.HOLDOVER
        val bindingState = when {
          identity == null -> "UDP_ONLY"
          seenAt == null -> "BLE_IDENTITY_KNOWN"
          metricReady -> "RANGE_READY"
          validFresh.isEmpty() -> "BLE_IDENTITY_SEEN"
          validFresh.size < MIN_SAMPLES_FOR_RANGE -> "SAMPLES_ACQUIRING"
          else -> "PROXIMITY_READY"
        }
        val blocker = when {
          temporalState == BleRangeTemporalState.HOLDOVER -> null
          temporalState == BleRangeTemporalState.EXPIRED || temporalState == BleRangeTemporalState.STALE -> "LAST_VALID_RANGE_EXPIRED"
          bindingState == "UDP_ONLY" -> "NO_BLE_IDENTITY"
          bindingState == "BLE_IDENTITY_KNOWN" -> "ADVERTISEMENT_NOT_SEEN"
          bindingState == "BLE_IDENTITY_SEEN" -> "STALE_SAMPLES"
          bindingState == "SAMPLES_ACQUIRING" -> "INSUFFICIENT_VALID_SAMPLES"
          bindingState == "PROXIMITY_READY" -> "NO_CURRENT_METRIC_RANGE"
          else -> null
        }
        val medianValid = validFresh.takeIf { it.isNotEmpty() }?.map { it.rssi.toDouble() }?.let { BleRangeEstimator.median(it) }
        val peerGapState = when {
          identity == null -> "NO_IDENTITY"
          lastValidSample == null -> "NO_VALID_RSSI_YET"
          now - lastValidSample.ms <= RANGE_FRESHNESS_MS -> "PEER_SAMPLE_HEALTHY"
          else -> "PEER_TEMPORARILY_NOT_OBSERVED"
        }
        val acquisitionStats = identity?.let { FabricRuntime.acquisitionStatsByIdentity[it] }
        val acquisitionBaseline = identity?.let { FabricRuntime.validationAcquisitionBaselineByIdentity[it] }
        val starvationBaseline = FabricRuntime.validationStarvationBaselineByPeer[peerId]
        fun starvationDelta(current: Long, baseline: Long?): Long = (current - (baseline ?: 0L)).coerceAtLeast(0L)
        val effectiveBaseline = if (ValidationRuntime.startedWallMs != null && acquisitionBaseline == null) {
          BleAcquisitionCounterSnapshot(0, 0, 0, 0, 0, 0, 0)
        } else acquisitionBaseline
        arr.put(JSONObject().apply {
          put("node_id", peerId)
          put("ble_identity", identity ?: JSONObject.NULL)
          put("address_fingerprint", address?.let { addressFingerprint(it) } ?: JSONObject.NULL)
          put("binding_state", bindingState)
          put("peer_gap_state", peerGapState)
          put("peer_health_state", FabricRuntime.peerHealthStateByPeer[peerId] ?: if (peerGapState == "PEER_SAMPLE_HEALTHY") PeerHealthState.PEER_HEALTHY.name else PeerHealthState.PEER_SPARSE.name)
          put("starvation_candidate_since_wall_ms", FabricRuntime.starvationCandidateSinceByPeer[peerId] ?: JSONObject.NULL)
          put("starvation_since_wall_ms", FabricRuntime.starvationSinceByPeer[peerId] ?: JSONObject.NULL)
          put("starvation_count", FabricRuntime.peerStarvationCountByPeer[peerId]?.get() ?: 0)
          put("starvation_recovery_participation_count", FabricRuntime.peerStarvationRecoveryParticipationByPeer[peerId]?.get() ?: 0)
          put("first_callback_after_recovery_count", FabricRuntime.peerStarvationRecoveryFirstValidByPeer[peerId]?.get() ?: 0)
          put("last_starvation_recovery_generation", FabricRuntime.peerLastStarvationRecoveryGeneration[peerId] ?: JSONObject.NULL)
          put("last_starvation_recovery_latency_ms", FabricRuntime.peerLastStarvationRecoveryLatencyMs[peerId] ?: JSONObject.NULL)
          put("run_starvation_count", starvationDelta(FabricRuntime.peerStarvationCountByPeer[peerId]?.get() ?: 0, starvationBaseline?.starvationCount))
          put("run_starvation_recovery_participation_count", starvationDelta(FabricRuntime.peerStarvationRecoveryParticipationByPeer[peerId]?.get() ?: 0, starvationBaseline?.recoveryParticipationCount))
          put("run_first_callback_after_recovery_count", starvationDelta(FabricRuntime.peerStarvationRecoveryFirstValidByPeer[peerId]?.get() ?: 0, starvationBaseline?.firstValidCallbackCount))
          put("run_starvation_recovery_success_count", starvationDelta(FabricRuntime.peerStarvationRecoverySuccessByPeer[peerId]?.get() ?: 0, starvationBaseline?.recoverySuccessCount))
          put("run_starvation_recovery_failure_count", starvationDelta(FabricRuntime.peerStarvationRecoveryFailureByPeer[peerId]?.get() ?: 0, starvationBaseline?.recoveryFailureCount))
          put("body_finder_scan_results_for_identity", identity?.let { FabricRuntime.bleSeenCountByIdentity[it]?.get() } ?: 0)
          put("raw_sample_count_5s", validFresh.size + invalidFresh.size)
          put("valid_rssi_sample_count_5s", validFresh.size)
          put("invalid_rssi_sample_count_5s", invalidFresh.size)
          put("raw_sample_count_8s", validRetained.size + invalidRetained.size)
          put("valid_rssi_sample_count_8s", validRetained.size)
          put("invalid_rssi_sample_count_8s", invalidRetained.size)
          put("sample_count_5s", validFresh.size)
          put("sample_count_8s", validRetained.size)
          put("last_sample_age_ms", if (lastValidSample == null) JSONObject.NULL else max(0L, now - lastValidSample.ms))
          put("latest_rssi_dbm", lastValidSample?.rssi ?: JSONObject.NULL)
          put("latest_valid_rssi_dbm", lastValidSample?.rssi ?: JSONObject.NULL)
          put("latest_invalid_rssi_dbm", lastInvalidSample?.rssi ?: JSONObject.NULL)
          put("median_rssi_dbm", medianValid ?: JSONObject.NULL)
          put("median_valid_rssi_dbm", medianValid ?: JSONObject.NULL)
          put("median_advertised_tx_power_dbm", validFresh.mapNotNull { sample -> sample.txPower.takeIf { it != Int.MIN_VALUE }?.toDouble() }.takeIf { it.isNotEmpty() }?.let { BleRangeEstimator.median(it) } ?: JSONObject.NULL)
          put("invalid_rssi_total_count", identity?.let { FabricRuntime.invalidRssiCountByIdentity[it]?.get() } ?: 0)
          put("fallback_evidence_ready", validFresh.size >= MIN_SAMPLES_FOR_RANGE)
          put("metric_range_ready", metricReady)
          put("metric_range_source", when (temporalState) {
            BleRangeTemporalState.FRESH -> "FRESH_ESTIMATE"
            BleRangeTemporalState.HOLDOVER -> "LAST_VALID_HOLDOVER"
            else -> JSONObject.NULL
          })
          put("range_temporal_state", temporalState.name)
          put("last_valid_range_age_ms", cachedAge ?: JSONObject.NULL)
          put("last_valid_distance_m", cached?.distanceM ?: JSONObject.NULL)
          put("last_valid_sigma_m", cached?.sigmaM ?: JSONObject.NULL)
          put("range_estimate", estimate?.toJson() ?: JSONObject.NULL)
          put("acquisition", acquisitionStats?.diagnostics(now, validFresh.size, validRetained.size, effectiveBaseline) ?: JSONObject.NULL)
          put("address_rebind_count", identity?.let { FabricRuntime.addressRebindCountByIdentity[it]?.get() } ?: 0)
          put("blocking_reason", blocker ?: JSONObject.NULL)
        })
      } catch (_: Throwable) {}
    }
    return arr
  }

  private fun rebindDiagnostics(): JSONArray {
    val arr = JSONArray()
    FabricRuntime.rebindEvents.forEach { event ->
      arr.put(
        JSONObject()
          .put("identity", event.identity)
          .put("previous_address_fingerprint", event.previousFingerprint)
          .put("new_address_fingerprint", event.newFingerprint)
          .put("wall_ms", event.wallMs)
          .put("reason", event.reason)
      )
    }
    return arr
  }

  private fun acquisitionProvenance(now: Long): JSONObject {
    val strategy = BleAcquisitionPolicy.currentStrategy()
    val (filterMode, hardwareFilterCount) = strategyFilterMode(strategy)
    val decision = strategyEnvironmentDecision(now)
    return JSONObject()
      .put("logical_acquisition_strategy", strategy.name)
      .put("strategy_since_wall_ms", BleAcquisitionPolicy.strategySinceMs())
      .put("strategy_reason", BleAcquisitionPolicy.lastStrategyReason())
      .put("active_recovery_generation", BleAcquisitionPolicy.activeRecoveryGeneration() ?: JSONObject.NULL)
      .put("strategy_recovery_generation", BleAcquisitionPolicy.strategyRecoveryGeneration() ?: JSONObject.NULL)
      .put("active_recovery_trigger_kind", BleAcquisitionPolicy.activeRecoveryTriggerKind()?.name ?: JSONObject.NULL)
      .put("active_recovery_trigger_peer_id", BleAcquisitionPolicy.activeRecoveryTriggerPeerId() ?: JSONObject.NULL)
      .put("recovery_started_wall_ms", BleAcquisitionPolicy.recoveryStartedMs() ?: JSONObject.NULL)
      .put("recovery_unfiltered_hard_limit_ms", BleAcquisitionPolicy.RECOVERY_UNFILTERED_WINDOW_MS)
      .put("recovery_unfiltered_action_target_ms", BleAcquisitionPolicy.RECOVERY_UNFILTERED_ACTION_TARGET_MS)
      .put("filtered_probe_exit_target_ms", BleAcquisitionPolicy.FILTERED_PROBE_EXIT_TARGET_MS)
      .put("filtered_probe_hard_limit_ms", BleAcquisitionPolicy.FILTERED_PROBE_WINDOW_MS)
      .put("filtered_probe_action_target_ms", BleAcquisitionPolicy.FILTERED_PROBE_ACTION_TARGET_MS)
      .put("recovery_budget_window_ms", BleAcquisitionPolicy.RECOVERY_ATTEMPT_WINDOW_MS)
      .put("recovery_budget_limit", BleAcquisitionPolicy.MAX_RECOVERY_ATTEMPTS_PER_5MIN)
      .put("recovery_attempts_in_current_5min_window_at_end", BleAcquisitionPolicy.recoveryAttemptsInWindow(now))
      .put("recovery_attempts_max_in_any_rolling_5min_window", BleAcquisitionPolicy.maxRecoveryAttemptsInAnyRollingWindow())
      .put("environment_authorization", JSONObject()
        .put("valid", decision.valid)
        .put("authorized", decision.authorized)
        .put("violation_type", decision.violationType ?: JSONObject.NULL)
        .put("authorization_reason", decision.authorizationReason))
      .put("android_scan_settings", JSONObject().put("scan_mode","LOW_LATENCY").put("callback_type","ALL_MATCHES").put("report_delay_ms",BleAcquisitionPolicy.REPORT_DELAY_MS).put("match_mode",BleAcquisitionPolicy.matchModeLabel()).put("num_matches",BleAcquisitionPolicy.numMatchesLabel()))
      .put("filter_configuration", JSONObject().put("mode", filterMode).put("hardware_filter_count", hardwareFilterCount).put("manufacturer_id",MANUFACTURER_ID).put("body_finder_prefix","4246"))
      .put("scan_generation", FabricRuntime.scanGeneration.get())
      .put("scanner_started_wall_ms", FabricRuntime.bleScanStartedWallMs ?: JSONObject.NULL)
  }

  private fun bleDiagnostics(ctx: Context, now: Long = System.currentTimeMillis()) = JSONObject().apply {
    put("permissions", JSONObject().apply {
      put("legacy_granted", legacyBluetoothPermissionsGranted(ctx))
      put("modern_granted", modernBluetoothPermissionsGranted(ctx))
      put("location_service_enabled", locationServiceEnabled(ctx) ?: JSONObject.NULL)
    })
    put("scan_state", FabricRuntime.bleScanState)
    put("advertise_state", FabricRuntime.bleAdvertiseState)
    put("scan_mode", FabricRuntime.bleScanMode)
    put("acquisition_provenance", acquisitionProvenance(now))
    put("scan_strategy", BleAcquisitionPolicy.currentStrategy().name)
    put("hardware_filter_count", if (BleAcquisitionPolicy.currentStrategy() == BleAcquisitionStrategy.UNFILTERED_RECOVERY) 0 else 1)
    put("match_mode", BleAcquisitionPolicy.matchModeLabel())
    put("num_matches", BleAcquisitionPolicy.numMatchesLabel())
    put("report_delay_ms", BleAcquisitionPolicy.REPORT_DELAY_MS)
    put("software_body_finder_filter", true)
    put("global_scanner_health", globalScannerHealth(now).name)
    put("body_finder_cohort_health", bodyFinderCohortHealth(now).name)
    put("scan_callback_health", globalScannerHealth(now).name)
    put("expected_known_peer_count", expectedKnownPeerCount())
    put("recent_known_peer_count", recentKnownPeerCount(now))
    put("last_bf_cohort_callback_age_ms", ageMs(now, FabricRuntime.lastBodyFinderScanResultWallMs))
    put("total_scan_results", FabricRuntime.totalScanResults.get())
    put("body_finder_scan_results", FabricRuntime.bodyFinderScanResults.get())
    put("malformed_body_finder_payloads", FabricRuntime.malformedBodyFinderPayloads.get())
    put("self_scan_results_ignored", FabricRuntime.selfScanResultsIgnored.get())
    put("invalid_rssi_total_count", FabricRuntime.invalidRssiTotalCount.get())
    put("last_any_scan_result_age_ms", ageMs(now, FabricRuntime.lastAnyScanResultWallMs))
    put("last_body_finder_scan_result_age_ms", ageMs(now, FabricRuntime.lastBodyFinderScanResultWallMs))
    put("last_valid_body_finder_rssi_age_ms", ageMs(now, FabricRuntime.lastValidBodyFinderRssiWallMs))
    put("scan_failure_code", FabricRuntime.bleScanFailureCode ?: JSONObject.NULL)
    put("scan_restart_count", FabricRuntime.scanRestartCount.get())
    put("advertise_failure_code", FabricRuntime.bleAdvertiseFailureCode ?: JSONObject.NULL)
    put("advertise_age_ms", ageMs(now, FabricRuntime.bleAdvertiseStartedWallMs))
    put("advertise_restart_count", FabricRuntime.advertiseRestartCount.get())
    put("advertise_mode", "LOW_LATENCY")
    put("advertise_tx_power", "MEDIUM_FROZEN_FOR_CALIBRATION")
    put("active_identity", bleIdentity())
    put("calibration_profile", BleRangeEstimator.profile.toJson())
    put("continuity_policy", JSONObject()
      .put("fresh_ms", BleContinuityPolicy.FRESH_MS)
      .put("holdover_max_ms", BleContinuityPolicy.HOLDOVER_MAX_MS)
      .put("hard_expiry_ms", BleContinuityPolicy.HARD_EXPIRY_MS)
      .put("sigma_aging_m_per_s", BleContinuityPolicy.SIGMA_AGING_M_PER_S)
      .put("holdover_sigma_cap_m", BleContinuityPolicy.HOLDOVER_SIGMA_CAP_M))
    put("acquisition_policy", BleAcquisitionPolicy.diagnostics(now)
      .put("primary_hardware_filter_count", 1)
      .put("recovery_hardware_filter_count", 0)
      .put("match_mode", BleAcquisitionPolicy.matchModeLabel())
      .put("num_matches", BleAcquisitionPolicy.numMatchesLabel())
      .put("report_delay_ms", BleAcquisitionPolicy.REPORT_DELAY_MS)
      .put("gap_1s_ms", BleAcquisitionPolicy.GAP_1S_MS)
      .put("gap_2s_ms", BleAcquisitionPolicy.GAP_2S_MS)
      .put("gap_5s_ms", BleAcquisitionPolicy.GAP_5S_MS)
      .put("gap_10s_ms", BleAcquisitionPolicy.GAP_10S_MS)
      .put("system_ranging_ble_yield_ms", BleAcquisitionPolicy.SYSTEM_RANGING_BLE_YIELD_MS))
    put("advertised_tx_power_semantics", "diagnostic transmitter metadata only; never used as RSSI@1m")
    put("peers", peerBleDiagnostics(now))
    put("rebind_events", rebindDiagnostics())
    put("system_ranging", if (Build.VERSION.SDK_INT >= 36) SystemRangingApi36.diagnostics(now) else JSONObject().put("state", "UNSUPPORTED").put("detail", "Android API < 36"))
  }

  private fun fabricDiagnostics(now: Long = System.currentTimeMillis()) = JSONObject().apply {
    put("socket_state", FabricRuntime.socketState)
    put("multicast_join_state", FabricRuntime.multicastJoinState)
    put("tx_packets", FabricRuntime.txPackets.get())
    put("rx_packets", FabricRuntime.rxPackets.get())
    put("rx_protocol_v2_packets", FabricRuntime.rxProtocolV2Packets.get())
    put("rx_same_session_packets", FabricRuntime.rxSameSessionPackets.get())
    put("peer_count_active", FabricRuntime.peers.size)
    put("peer_expire_count", FabricRuntime.peerExpireCount.get())
    put("wire_transport_v11", WireTransportV10.telemetry())
    val peers = JSONArray()
    FabricRuntime.peerPacketCounts.forEach { (nodeId, count) ->
      val lastSeen = FabricRuntime.peerLastSeenWallMs[nodeId]
      peers.put(JSONObject()
        .put("node_id", nodeId)
        .put("last_seen_age_ms", ageMs(now, lastSeen))
        .put("packets_received", count.get())
        .put("state", when {
          !FabricRuntime.peers.containsKey(nodeId) -> "EXPIRED"
          FabricRuntime.peerStaleSinceWallMs.containsKey(nodeId) -> "STALE"
          else -> "ACTIVE"
        }))
    }
    put("peers", peers)
  }

  private fun validationRunDiagnostics(ctx: Context, now: Long = System.currentTimeMillis()): JSONObject {
    if (ValidationRuntime.runId != null && ValidationRuntime.endedWallMs == null) {
      val (issues, decision) = validationEnvironmentIssues(ctx, now)
      ValidationRuntime.recordEnvironmentEvaluation(
        now, issues, decision, BleAcquisitionPolicy.currentStrategy(),
        BleAcquisitionPolicy.activeRecoveryGeneration(), BleAcquisitionPolicy.activeRecoveryTriggerKind(), BleAcquisitionPolicy.activeRecoveryTriggerPeerId(), ctx,
      )
    }
    val out=ValidationRuntime.diagnostics(now,FabricRuntime.peerExpireCount.get(),FabricRuntime.totalRebinds(),FabricRuntime.scanRestartCount.get(),FabricRuntime.txPackets.get(),FabricRuntime.rxPackets.get())
    if(!out.optBoolean("snapshot_frozen")) out.put("acquisition_strategy",BleAcquisitionPolicy.currentStrategy().name).put("body_finder_cohort_health",bodyFinderCohortHealth(now).name)
    return out
  }

  private fun lifecycleDiagnostics(ctx: Context): JSONObject =
    FieldServiceState.diagnostics(ctx).put("app_visibility", ValidationRuntime.appVisibility)

  private fun diagnostics(ctx: Context): JSONObject {
    val now = System.currentTimeMillis()
    val evidenceReady = fallbackEvidenceReadyCount(now)
    val freshMetricReady = freshMetricReadyCount(now)
    val usableMetricReady = metricReadyCount(now)
    ValidationRuntime.observe(now, FabricRuntime.peers.size, evidenceReady, freshMetricReady, usableMetricReady)
    return JSONObject()
      .put("diagnostic_contract", JSONObject()
        .put("schema", "dev20.10-self-contained-json-evidence-v13")
        .put("screenshots_required", false)
        .put("json_self_contained", true)
        .put("contains_runtime_preflight", true)
        .put("contains_system_ranging", true)
        .put("contains_recovery_causality", true)
        .put("contains_frozen_geometry", true))
      .put("validation_preflight", validationPreflight(ctx, now).put("runtime_live", true).put("not_acceptance_evidence", true))
      .put("evidence_contract", JSONObject().put("schema", "dev20.10-self-contained-json-evidence-v13").put("screenshots_required", false).put("json_self_contained", true))
      .put("ble_diagnostics", bleDiagnostics(ctx, now))
      .put("fabric_diagnostics", fabricDiagnostics(now))
      .put("lifecycle_diagnostics", lifecycleDiagnostics(ctx))
      .put("selected_validation_run_id", ValidationRuntime.selectedRunId() ?: JSONObject.NULL)
      .put("completed_validation_runs_summary", ValidationRuntime.completedRunsSummary())
      .put("validation_run", validationRunDiagnostics(ctx, now))
  }

  private fun calibrationSnapshot(now: Long = System.currentTimeMillis()): JSONObject {
    val peers = JSONArray()
    FabricRuntime.peers.values.forEach { pair ->
      try {
        val peer = JSONObject(pair.first)
        val identity = peer.optString("ble_identity").takeIf { it.isNotBlank() && it != "null" } ?: return@forEach
        val fresh = validSamples(identity, now, WINDOW_RETENTION_MS)
        val invalid = invalidEvents(identity, now, WINDOW_RETENTION_MS)
        val tx = fresh.mapNotNull { sample -> sample.txPower.takeIf { it != Int.MIN_VALUE }?.toDouble() }
        val estimate = BleRangeEstimator.estimate(
          fresh.map { it.rssi.toDouble() },
          tx,
          MIN_SAMPLES_FOR_RANGE,
        )
        peers.put(
          JSONObject()
            .put("observer_node_id", FabricRuntime.nodeId)
            .put("peer_node_id", peer.optString("node_id"))
            .put("peer_display_name", peer.optString("display_name"))
            .put("ble_identity", identity)
            .put("sample_count", fresh.size)
            .put("valid_rssi_sample_count", fresh.size)
            .put("invalid_rssi_sample_count", invalid.size)
            .put("rssi_samples_dbm", JSONArray(fresh.map { it.rssi }))
            .put("advertised_tx_power_samples_dbm", JSONArray(tx))
            .put("estimate", estimate.toJson())
        )
      } catch (_: Throwable) {}
    }
    return JSONObject()
      .put("schema_version", 2)
      .put("captured_wall_ms", now)
      .put("session_id", FabricRuntime.sessionId)
      .put("observer_node_id", FabricRuntime.nodeId)
      .put("observer_display_name", FabricRuntime.displayName)
      .put("calibration_profile", BleRangeEstimator.profile.toJson())
      .put("peers", peers)
      .put("invalid_rssi_values_exported", false)
      .put("ground_truth_in_runtime", false)
  }

  private fun advertisement(ctx: Context) = JSONObject().apply {
    put("protocol_version", PROTOCOL)
    put("session_id", FabricRuntime.sessionId)
    put("node_id", FabricRuntime.nodeId)
    put("display_name", FabricRuntime.displayName)
    put("platform", "android")
    put("monotonic_ns", SystemClock.elapsedRealtimeNanos())
    put("coordinator_score", 0.78)
    put("capabilities", capabilityMap(ctx))
    val rssi = wifiRssi(ctx)
    if (rssi == null) put("rssi_dbm", JSONObject.NULL) else put("rssi_dbm", rssi)
    if (FabricRuntime.baseline == null) put("baseline_rssi_dbm", JSONObject.NULL) else put("baseline_rssi_dbm", FabricRuntime.baseline)
    if (FabricRuntime.sigma == null) put("baseline_sigma_db", JSONObject.NULL) else put("baseline_sigma_db", FabricRuntime.sigma)
    put("position", JSONObject.NULL)
    put("scanning", FabricRuntime.scanning)
    put("ble_identity", bleIdentity())
    put("wire_transport_v11", WireTransportV10.telemetry())
    put("ranges", rangeObservations())
    put("manual_geometry_override", false)
    val controlPlane = FabricRuntime.controlPlaneJson
    if (controlPlane != null) {
      try { put("control_plane", JSONObject(controlPlane)) } catch (_: Throwable) { put("control_plane", JSONObject.NULL) }
    } else put("control_plane", JSONObject.NULL)
    val published = FabricRuntime.publishedGeometryJson
    if (published != null) {
      try {
        put("geometry_publisher_node_id", FabricRuntime.nodeId)
        put("published_geometry", JSONObject(published))
      } catch (_: Throwable) {
        put("geometry_publisher_node_id", JSONObject.NULL)
        put("published_geometry", JSONObject.NULL)
      }
    } else {
      put("geometry_publisher_node_id", JSONObject.NULL)
      put("published_geometry", JSONObject.NULL)
    }
  }

  private fun fabricTransitionDetails(ctx: Context, now: Long, nodeId: String, payload: String?, lastRxWallMs: Long?, stateBefore: String, stateAfter: String, reason: String): JSONObject {
    val peer = try { payload?.let(::JSONObject) } catch (_: Throwable) { null }
    val identity = peer?.optString("ble_identity")?.takeIf { it.isNotBlank() && it != "null" }
    val bleLast = identity?.let { FabricRuntime.lastValidRssiWallMsByIdentity[it] }
    val ranging = if (Build.VERSION.SDK_INT >= 36) SystemRangingApi36.diagnostics(now) else JSONObject().put("state", "UNSUPPORTED")
    return JSONObject()
      .put("wall_ms", now)
      .put("peer_id", nodeId)
      .put("reason", reason)
      .put("last_rx_wall_ms", lastRxWallMs ?: JSONObject.NULL)
      .put("last_rx_monotonic_ns", FabricRuntime.peerLastSeenMonotonicNs[nodeId] ?: JSONObject.NULL)
      .put("rx_gap_ms_at_transition", lastRxWallMs?.let { (now - it).coerceAtLeast(0L) } ?: JSONObject.NULL)
      .put("rx_packets_at_transition", FabricRuntime.peerPacketCounts[nodeId]?.get() ?: 0L)
      .put("peer_state_before", stateBefore)
      .put("peer_state_after", stateAfter)
      .put("expected_peer_count_at_start", ValidationRuntime.frozenExpectedPeerCount())
      .put("expected_peer_ids_at_start", JSONArray(ValidationRuntime.frozenExpectedPeerIds()))
      .put("active_peer_count_at_transition", FabricRuntime.peers.size)
      .put("scan_generation", FabricRuntime.scanGeneration.get())
      .put("ranging_manager_state", ranging.optString("state"))
      .put("ranging_yield_active", ranging.optBoolean("ble_yield_active"))
      .put("system_ranging", ranging)
      .put("ble_identity", identity ?: JSONObject.NULL)
      .put("ble_last_sample_age_ms", bleLast?.let { (now - it).coerceAtLeast(0L) } ?: JSONObject.NULL)
      .put("socket_state", FabricRuntime.socketState)
      .put("multicast_join_state", FabricRuntime.multicastJoinState)
      .put("lifecycle", lifecycleDiagnostics(ctx))
  }

  private fun expirePeers(ctx: Context, now: Long) {
    FabricRuntime.peers.entries.forEach { entry ->
      val nodeId = entry.key
      val gap = now - entry.value.second
      if (gap > PEER_STALE_MS && gap <= PEER_EXPIRY_MS && FabricRuntime.peerStaleSinceWallMs.putIfAbsent(nodeId, now) == null) {
        FabricEventTimeline.record(
          "PEER_BECAME_STALE",
          fabricTransitionDetails(ctx, now, nodeId, entry.value.first, entry.value.second, "ACTIVE", "STALE", "UDP_RX_GAP_EXCEEDED_STALE_THRESHOLD")
        )
      }
    }
    val expired = FabricRuntime.peers.entries
      .filter { now - it.value.second > PEER_EXPIRY_MS }
      .map { it.key }
    for (nodeId in expired) {
      val pair = FabricRuntime.peers[nodeId]
      val lastSeen = pair?.second ?: FabricRuntime.peerLastSeenWallMs[nodeId]
      if (pair != null) {
        FabricEventTimeline.record(
          "PEER_EXPIRED",
          fabricTransitionDetails(ctx, now, nodeId, pair.first, lastSeen, if (FabricRuntime.peerStaleSinceWallMs.containsKey(nodeId)) "STALE" else "ACTIVE", "EXPIRED", "UDP_RX_GAP_EXCEEDED_HARD_EXPIRY")
        )
      }
      if (FabricRuntime.peers.remove(nodeId) != null) {
        FabricRuntime.peerExpireCount.incrementAndGet()
        FabricRuntime.peerStaleSinceWallMs.remove(nodeId)
        FabricRuntime.lastValidRangeByPeer.remove(nodeId)
      }
    }
  }

  private fun startFieldService(ctx: Context) {
    try {
      val intent = Intent(ctx, BodyFinderFieldService::class.java).setAction(BodyFinderFieldService.ACTION_START)
      if (Build.VERSION.SDK_INT >= 26) ctx.startForegroundService(intent) else ctx.startService(intent)
    } catch (e: Throwable) {
      FieldServiceState.state = "FAILED"
      FieldServiceState.lastError = "${e.javaClass.simpleName}: ${e.message}"
    }
  }

  private fun stopFieldService(ctx: Context) {
    try {
      val intent = Intent(ctx, BodyFinderFieldService::class.java).setAction(BodyFinderFieldService.ACTION_STOP)
      ctx.startService(intent)
    } catch (_: Throwable) {
      try { ctx.stopService(Intent(ctx, BodyFinderFieldService::class.java)) } catch (_: Throwable) {}
    }
  }

  private fun startNetworkThread(ctx: Context) {
    thread(name = "BodyFinderFabricV2", isDaemon = true) {
      try {
        val socket = MulticastSocket(null)
        socket.reuseAddress = true
        socket.broadcast = true
        socket.bind(InetSocketAddress(PORT))
        FabricRuntime.socketState = "BOUND"
        try {
          socket.joinGroup(InetAddress.getByName(GROUP))
          FabricRuntime.multicastJoinState = "JOINED"
        } catch (e: Throwable) {
          FabricRuntime.multicastJoinState = "FAILED:${e.javaClass.simpleName}"
        }
        socket.soTimeout = 250
        FabricRuntime.socket = socket
        val groupAddress = InetAddress.getByName(GROUP)
        val broadcastAddress = InetAddress.getByName("255.255.255.255")
        val buffer = ByteArray(65507)
        var nextSend = 0L
        var nextSystemRangingRefresh = 0L
        while (FabricRuntime.running) {
          val now = System.currentTimeMillis()
          maintainAdaptiveScanner(ctx, now)
          if (ValidationRuntime.runId != null && ValidationRuntime.endedWallMs == null) {
            val (issues, decision) = validationEnvironmentIssues(ctx, now)
            ValidationRuntime.recordEnvironmentEvaluation(
              now, issues, decision, BleAcquisitionPolicy.currentStrategy(),
              BleAcquisitionPolicy.activeRecoveryGeneration(), BleAcquisitionPolicy.activeRecoveryTriggerKind(), BleAcquisitionPolicy.activeRecoveryTriggerPeerId(), ctx,
            )
          }
          if (Build.VERSION.SDK_INT >= 36 && now >= nextSystemRangingRefresh && hasPermission(ctx, RANGE_PERMISSION)) {
            try { SystemRangingApi36.refresh(ctx, desiredSystemRangingPeers()) } catch (_: Throwable) {}
            nextSystemRangingRefresh = now + 1_000L
          }
          if (now >= nextSend) {
            val ad = advertisement(ctx)
            try {
              val frames = WireTransportV10.frames(ad, FabricRuntime.nodeId, FabricRuntime.sessionId, now)
              WireTransportV10.send(socket, groupAddress, PORT, frames)
              WireTransportV10.send(socket, broadcastAddress, PORT, frames)
            } catch (t: Throwable) {
              WireTransportV10.sendErrorCount.incrementAndGet()
              WireTransportV10.lastSendError = "${t.javaClass.simpleName}:${t.message}"
            }
            nextSend = now + 800L
          }
          try {
            val packet = DatagramPacket(buffer, buffer.size)
            socket.receive(packet)
            FabricRuntime.rxPackets.incrementAndGet()
            val text = String(packet.data, packet.offset, packet.length, Charsets.UTF_8)
            val consumed = WireTransportV10.consume(text, packet.address)
            for (reply in consumed.replies) WireTransportV10.send(socket, reply.address, PORT, listOf(reply.frame))
            val obj = consumed.document ?: continue
            if (obj.optInt("protocol_version") == PROTOCOL) FabricRuntime.rxProtocolV2Packets.incrementAndGet()
            val remoteId = obj.optString("node_id")
            if (obj.optInt("protocol_version") == PROTOCOL && obj.optString("session_id") == FabricRuntime.sessionId) {
              FabricRuntime.rxSameSessionPackets.incrementAndGet()
            }
            if (obj.optInt("protocol_version") == PROTOCOL &&
              obj.optString("session_id") == FabricRuntime.sessionId &&
              remoteId.isNotBlank() && remoteId != FabricRuntime.nodeId
            ) {
              val seen = System.currentTimeMillis()
              val previousPair = FabricRuntime.peers[remoteId]
              val previousLastSeen = FabricRuntime.peerLastSeenWallMs[remoteId]
              val wasKnown = FabricRuntime.peerPacketCounts.containsKey(remoteId)
              val wasActive = previousPair != null
              val wasStale = FabricRuntime.peerStaleSinceWallMs.containsKey(remoteId)
              val peerPayload = obj.toString()
              FabricRuntime.peers[remoteId] = peerPayload to seen
              FabricRuntime.peerLastSeenWallMs[remoteId] = seen
              FabricRuntime.peerLastSeenMonotonicNs[remoteId] = SystemClock.elapsedRealtimeNanos()
              FabricRuntime.peerPacketCounts.computeIfAbsent(remoteId) { AtomicLong(0) }.incrementAndGet()
              if (wasKnown && (!wasActive || wasStale)) {
                FabricEventTimeline.record(
                  "PEER_REACTIVATED",
                  fabricTransitionDetails(ctx, seen, remoteId, peerPayload, previousLastSeen, if (!wasActive) "EXPIRED" else "STALE", "ACTIVE", "UDP_RX_RESUMED")
                )
              }
              FabricRuntime.peerStaleSinceWallMs.remove(remoteId)
            }
          } catch (_: java.net.SocketTimeoutException) {
          } catch (t: Throwable) { WireTransportV10.noteReceiveError(t) }
          for (reply in WireTransportV10.maintenance(now)) WireTransportV10.send(socket, reply.address, PORT, listOf(reply.frame))
          expirePeers(ctx, now)
        }
      } catch (e: Throwable) {
        FabricRuntime.socketState = "FAILED:${e.javaClass.simpleName}"
      } finally {
        if (Build.VERSION.SDK_INT >= 36) {
          try { SystemRangingApi36.stop() } catch (_: Throwable) {}
        }
        try { FabricRuntime.socket?.close() } catch (_: Throwable) {}
        FabricRuntime.socket = null
        FabricRuntime.socketState = "CLOSED"
      }
    }
  }
}
