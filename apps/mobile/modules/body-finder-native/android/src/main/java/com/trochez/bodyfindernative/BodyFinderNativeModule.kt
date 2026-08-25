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
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.location.LocationManager
import android.net.wifi.WifiManager
import android.os.Build
import android.os.PowerManager
import android.os.SystemClock
import android.view.WindowManager
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import org.json.JSONArray
import org.json.JSONObject
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
private const val PEER_EXPIRY_MS = 5_000L
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
  @Volatile private var baselinePeerStarvation: Long = 0
  @Volatile private var baselinePeerStarvationRequests: Long = 0
  @Volatile private var baselinePeerStarvationSuccesses: Long = 0
  @Volatile private var baselinePeerStarvationFailures: Long = 0
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
    val ps=PeerStarvationRecovery.counters()
    baselinePeerStarvation=ps[1]; baselinePeerStarvationRequests=ps[2]; baselinePeerStarvationSuccesses=ps[3]; baselinePeerStarvationFailures=ps[4]
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
      .put("peer_starvation_delta", base.optLong("peer_starvation_delta"))
      .put("peer_starvation_recovery_request_delta", base.optLong("peer_starvation_recovery_request_delta"))
      .put("peer_starvation_recovery_success_delta", base.optLong("peer_starvation_recovery_success_delta"))
      .put("peer_starvation_recovery_failure_delta", base.optLong("peer_starvation_recovery_failure_delta"))
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
      .put("acceptance_minimum_ms", 300000L)
      .put("acceptance_duration_eligible", elapsed >= 300000L)
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
      .put("peer_starvation_delta", (PeerStarvationRecovery.counters()[1]-baselinePeerStarvation).coerceAtLeast(0))
      .put("peer_starvation_recovery_request_delta", (PeerStarvationRecovery.counters()[2]-baselinePeerStarvationRequests).coerceAtLeast(0))
      .put("peer_starvation_recovery_success_delta", (PeerStarvationRecovery.counters()[3]-baselinePeerStarvationSuccesses).coerceAtLeast(0))
      .put("peer_starvation_recovery_failure_delta", (PeerStarvationRecovery.counters()[4]-baselinePeerStarvationFailures).coerceAtLeast(0))
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

private object FabricRuntime {
  @Volatile var running = false
  @Volatile var nodeId = UUID.randomUUID().toString()
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
  val validationStarvationBaselineByPeer = ConcurrentHashMap<String, LongArray>()
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
    bleLastSeenWallMsByIdentity.clear()
    bleSeenCountByIdentity.clear()
    acquisitionStatsByIdentity.clear()
    validationAcquisitionBaselineByIdentity.clear()
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
    validationStarvationBaselineByPeer.clear()
    peers.values.forEach { pair -> try { val id=JSONObject(pair.first).optString("node_id"); if(id.isNotBlank()) validationStarvationBaselineByPeer[id]=PeerStarvationRecovery.peerCounters(id) } catch(_:Throwable){} }
    acquisitionStatsByIdentity.forEach { (identity, stats) ->
      validationAcquisitionBaselineByIdentity[identity] = stats.snapshot()
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
    stopBle()
  }
}

class BodyFinderNativeModule : Module() {
  override fun definition() = ModuleDefinition {
    Name("BodyFinderNative")

    Function("getCapabilitiesJson") {
      val ctx = appContext.reactContext ?: return@Function "{}"
      deviceReport(ctx).toString()
    }
    Function("getDiagnosticsJson") {
      val ctx = appContext.reactContext ?: return@Function "{}"
      diagnostics(ctx).toString()
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
      ValidationRuntime.appVisibility = visibility
      true
    }
    Function("startValidationRun") {
      val ctx = appContext.reactContext ?: return@Function "VALIDATION_ENVIRONMENT_INVALID:NO_CONTEXT"
      val issues = validationEnvironmentIssues(ctx)
      if (issues.isNotEmpty()) return@Function "VALIDATION_ENVIRONMENT_INVALID:${issues.joinToString(",")}"
      val now = System.currentTimeMillis()
      FabricRuntime.snapshotAcquisitionForValidation()
      keepValidationScreenAwake(true)
      ValidationRuntime.start(
        now,
        FabricRuntime.peerExpireCount.get(),
        FabricRuntime.totalRebinds(),
        FabricRuntime.scanRestartCount.get(),
        FabricRuntime.txPackets.get(),
        FabricRuntime.rxPackets.get(),
      )
    }
    Function("endValidationRun") {
      val ctx = appContext.reactContext ?: return@Function false
      val now=System.currentTimeMillis()
      ValidationRuntime.end(now,FabricRuntime.peerExpireCount.get(),FabricRuntime.totalRebinds(),FabricRuntime.scanRestartCount.get(),FabricRuntime.txPackets.get(),FabricRuntime.rxPackets.get(),acquisitionProvenance(now),peerBleDiagnostics(now),if(Build.VERSION.SDK_INT>=36) SystemRangingApi36.diagnostics(now) else JSONObject().put("state","UNSUPPORTED"))
      keepValidationScreenAwake(false)
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
      if (ctx != null) stopFieldService(ctx.applicationContext)
      keepValidationScreenAwake(false)
      FabricRuntime.stop()
      true
    }
    Function("getPeersJson") {
      expirePeers(System.currentTimeMillis())
      val arr = JSONArray()
      FabricRuntime.peers.values.forEach { pair ->
        try { arr.put(JSONObject(pair.first)) } catch (_: Throwable) {}
      }
      arr.toString()
    }
    Function("getLocalAdvertisementJson") {
      val ctx = appContext.reactContext ?: return@Function "{}"
      advertisement(ctx).toString()
    }
  }

  private fun keepValidationScreenAwake(enable:Boolean){
    val a=appContext.currentActivity ?: return
    a.runOnUiThread { if(enable) a.window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON) else a.window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON) }
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

  private fun validationEnvironmentIssues(ctx: Context): List<String> {
    val issues = mutableListOf<String>()
    val power = ctx.getSystemService(Context.POWER_SERVICE) as? PowerManager
    if (power?.isPowerSaveMode == true) issues += "BATTERY_SAVER_ON"
    if (power != null && !power.isInteractive) issues += "SCREEN_OFF"
    if (ValidationRuntime.appVisibility != "active") issues += "APP_NOT_FOREGROUND"
    if (FieldServiceState.state != "RUNNING") issues += "FIELD_SERVICE_NOT_RUNNING"
    val manager = ctx.getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager
    if (manager?.adapter?.isEnabled != true) issues += "BLUETOOTH_OFF"
    return issues
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

  private fun peerStarvationCandidate(now:Long):String? {
    if(globalScannerHealth(now)!=GlobalBleScannerHealth.GLOBAL_SCANNER_HEALTHY) return null
    for(pair in FabricRuntime.peers.values){
      try{
        val peer=JSONObject(pair.first); val peerId=peer.optString("node_id"); val identity=peer.optString("ble_identity")
        if(peerId.isBlank()||identity.isBlank()||identity=="null") continue
        val fabricSeen=FabricRuntime.peerLastSeenWallMs[peerId] ?: pair.second
        val fabricActive=now-fabricSeen<=PEER_EXPIRY_MS
        val bound=FabricRuntime.bleAddressByIdentity.containsKey(identity) || FabricRuntime.lastValidRssiWallMsByIdentity.containsKey(identity)
        val valid5=validSamples(identity,now,RANGE_FRESHNESS_MS).size
        val last=FabricRuntime.lastValidRssiWallMsByIdentity[identity]
        val age=last?.let{max(0L,now-it)}
        val d=PeerStarvationRecovery.observe(peerId,now,fabricActive,bound,true,valid5,age,BleAcquisitionPolicy.activeRecoveryGeneration()!=null)
        if(d.state==PeerHealthState.PEER_STARVED && d.requestRecovery) return peerId
      }catch(_:Throwable){}
    }
    return null
  }

  private fun targetRecoverySatisfied(now:Long):Boolean {
    val started=BleAcquisitionPolicy.recoveryStartedMs() ?: return false
    val target=BleAcquisitionPolicy.lastRecoveryTriggerPeerId()
    if(BleAcquisitionPolicy.lastRecoveryTriggerKind()!=RecoveryTriggerKind.PEER_STARVATION || target==null) return recentKnownPeerCount(now)>0 && FabricRuntime.lastBodyFinderScanResultWallMs?.let{it>=started}==true
    val pair=FabricRuntime.peers.values.firstOrNull{ try{JSONObject(it.first).optString("node_id")==target}catch(_:Throwable){false} } ?: return false
    val identity=try{JSONObject(pair.first).optString("ble_identity")}catch(_:Throwable){return false}
    val last=FabricRuntime.lastValidRssiWallMsByIdentity[identity] ?: return false
    if(last<started) return false
    BleAcquisitionPolicy.noteValidCallback(target,last)
    return true
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

    if (global == GlobalBleScannerHealth.GLOBAL_SCANNER_STALLED) {
      if (now - FabricRuntime.lastScanRestartWallMs >= BleAcquisitionPolicy.MIN_RESTART_COOLDOWN_MS) {
        restartScannerWithStrategy(now, BleAcquisitionStrategy.FILTERED_PRIMARY, "GLOBAL_SCANNER_STALLED")
      }
      return
    }

    when (BleAcquisitionPolicy.currentStrategy()) {
      BleAcquisitionStrategy.FILTERED_PRIMARY -> {
        if (cohort == BodyFinderCohortHealth.BF_COHORT_STALLED) {
          if (BleAcquisitionPolicy.canStartRecovery(now)) {
            BleAcquisitionPolicy.beginRecovery(now, "BF_COHORT_STALLED", RecoveryTriggerKind.FULL_COHORT_STALL, null)
            restartScannerWithStrategy(now, BleAcquisitionStrategy.UNFILTERED_RECOVERY, "BF_COHORT_STALLED")
          } else if(BleAcquisitionPolicy.recoveryAttemptsInWindow(now)>=BleAcquisitionPolicy.MAX_RECOVERY_ATTEMPTS_PER_5MIN) BleAcquisitionPolicy.markFailedSafe(now,"MAX_RECOVERY_ATTEMPTS")
        } else {
          val starved=peerStarvationCandidate(now)
          if(starved!=null && BleAcquisitionPolicy.canStartRecovery(now)){
            BleAcquisitionPolicy.beginRecovery(now,"PEER_STARVATION",RecoveryTriggerKind.PEER_STARVATION,starved)
            restartScannerWithStrategy(now,BleAcquisitionStrategy.UNFILTERED_RECOVERY,"PEER_STARVATION:$starved")
          }
        }
      }
      BleAcquisitionStrategy.UNFILTERED_RECOVERY -> {
        val started = BleAcquisitionPolicy.recoveryStartedMs() ?: now
        val recovered = targetRecoverySatisfied(now)
        if (recovered) {
          BleAcquisitionPolicy.noteRecoverySuccess(now)
          restartScannerWithStrategy(now, BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE, "BF_COHORT_RECOVERED")
        } else if (now - started >= BleAcquisitionPolicy.RECOVERY_UNFILTERED_WINDOW_MS) {
          BleAcquisitionPolicy.noteRecoveryFailure(now)
          restartScannerWithStrategy(now, BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE, "RECOVERY_WINDOW_EXPIRED")
        }
      }
      BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE -> {
        cohort = bodyFinderCohortHealth(now)
        if (cohort == BodyFinderCohortHealth.BF_COHORT_STALLED) {
          if (BleAcquisitionPolicy.canStartRecovery(now)) {
            BleAcquisitionPolicy.beginRecovery(now, "PROBE_STALLED", RecoveryTriggerKind.FULL_COHORT_STALL, null)
            restartScannerWithStrategy(now, BleAcquisitionStrategy.UNFILTERED_RECOVERY, "PROBE_STALLED")
          } else {
            BleAcquisitionPolicy.transition(BleAcquisitionStrategy.COOLDOWN, now, "RECOVERY_COOLDOWN")
          }
        } else if (now - BleAcquisitionPolicy.strategySinceMs() >= BleAcquisitionPolicy.FILTERED_PROBE_WINDOW_MS) {
          BleAcquisitionPolicy.transition(BleAcquisitionStrategy.FILTERED_PRIMARY, now, "PROBE_STABLE")
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
    if (validRssi && BleAcquisitionPolicy.currentStrategy() == BleAcquisitionStrategy.UNFILTERED_RECOVERY) ValidationEventLog.record("FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY", "BODY_FINDER_CALLBACK", now = now)
    FabricRuntime.acquisitionStatsByIdentity.computeIfAbsent(id) { BleAcquisitionStats() }.record(now, validRssi, BleAcquisitionPolicy.currentStrategy())

    val advertisedTx = result.scanRecord?.txPowerLevel?.takeIf { it in -100..20 } ?: Int.MIN_VALUE
    if (validRssi) {
      val queue = FabricRuntime.rssiWindows.computeIfAbsent(id) { ConcurrentLinkedDeque() }
      queue.addLast(RssiSample(result.rssi, advertisedTx, now))
      FabricRuntime.lastValidRssiWallMsByIdentity[id] = now
      FabricRuntime.lastValidBodyFinderRssiWallMs = now
      trimValidQueue(queue, now)
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
        val effectiveBaseline = if (ValidationRuntime.startedWallMs != null && acquisitionBaseline == null) {
          BleAcquisitionCounterSnapshot(0, 0, 0, 0, 0, 0, 0)
        } else acquisitionBaseline
        arr.put(JSONObject().apply {
          put("node_id", peerId)
          put("ble_identity", identity ?: JSONObject.NULL)
          put("address_fingerprint", address?.let { addressFingerprint(it) } ?: JSONObject.NULL)
          put("binding_state", bindingState)
          put("peer_gap_state", peerGapState)
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
          val starvation=PeerStarvationRecovery.diagnostics(peerId)
          val ps=PeerStarvationRecovery.peerCounters(peerId); val pb=FabricRuntime.validationStarvationBaselineByPeer[peerId] ?: longArrayOf(0,0,0,0)
          put("peer_health_state",starvation.optString("peer_health_state"))
          put("starvation_candidate_since_wall_ms",starvation.opt("starvation_candidate_since_wall_ms"))
          put("starvation_since_wall_ms",starvation.opt("starvation_since_wall_ms"))
          put("starvation_count",ps[0])
          put("starvation_recovery_participation_count",ps[1])
          put("last_starvation_recovery_generation",starvation.opt("last_starvation_recovery_generation"))
          put("last_starvation_recovery_latency_ms",starvation.opt("last_starvation_recovery_latency_ms"))
          put("run_starvation_count",(ps[0]-pb[0]).coerceAtLeast(0))
          put("run_starvation_recovery_participation_count",(ps[1]-pb[1]).coerceAtLeast(0))
          put("run_starvation_recovery_success_count",(ps[2]-pb[2]).coerceAtLeast(0))
          put("run_starvation_recovery_failure_count",(ps[3]-pb[3]).coerceAtLeast(0))
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

  private fun acquisitionProvenance(now:Long)=JSONObject()
    .put("logical_acquisition_strategy",BleAcquisitionPolicy.currentStrategy().name)
    .put("strategy_since_wall_ms",BleAcquisitionPolicy.strategySinceMs())
    .put("strategy_reason",BleAcquisitionPolicy.lastStrategyReason())
    .put("android_scan_settings",JSONObject().put("scan_mode","LOW_LATENCY").put("callback_type","ALL_MATCHES").put("report_delay_ms",BleAcquisitionPolicy.REPORT_DELAY_MS).put("match_mode",BleAcquisitionPolicy.matchModeLabel()).put("num_matches",BleAcquisitionPolicy.numMatchesLabel()))
    .put("filter_configuration",JSONObject().put("mode",if(BleAcquisitionPolicy.currentStrategy()==BleAcquisitionStrategy.UNFILTERED_RECOVERY) "UNFILTERED" else "MANUFACTURER_FILTERED").put("hardware_filter_count",if(BleAcquisitionPolicy.currentStrategy()==BleAcquisitionStrategy.UNFILTERED_RECOVERY)0 else 1).put("manufacturer_id",MANUFACTURER_ID).put("body_finder_prefix","4246"))
    .put("scan_generation",FabricRuntime.scanGeneration.get()).put("scanner_started_wall_ms",FabricRuntime.bleScanStartedWallMs ?: JSONObject.NULL)

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
    val peers = JSONArray()
    FabricRuntime.peerPacketCounts.forEach { (nodeId, count) ->
      val lastSeen = FabricRuntime.peerLastSeenWallMs[nodeId]
      peers.put(JSONObject()
        .put("node_id", nodeId)
        .put("last_seen_age_ms", ageMs(now, lastSeen))
        .put("packets_received", count.get())
        .put("state", if (FabricRuntime.peers.containsKey(nodeId)) "ACTIVE" else "EXPIRED"))
    }
    put("peers", peers)
  }

  private fun preflightDiagnostics(ctx:Context,now:Long):JSONObject {
    val issues=validationEnvironmentIssues(ctx)
    val manager=ctx.getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager
    val expected=expectedKnownPeerCount()
    return JSONObject()
      .put("valid",issues.isEmpty() && expected>=2 && BleAcquisitionPolicy.currentStrategy()==BleAcquisitionStrategy.FILTERED_PRIMARY)
      .put("bluetooth_on",manager?.adapter?.isEnabled==true)
      .put("battery_saver_off",(ctx.getSystemService(Context.POWER_SERVICE) as? PowerManager)?.isPowerSaveMode!=true)
      .put("screen_on",(ctx.getSystemService(Context.POWER_SERVICE) as? PowerManager)?.isInteractive==true)
      .put("app_foreground",ValidationRuntime.appVisibility=="active")
      .put("foreground_service_running",FieldServiceState.state=="RUNNING")
      .put("expected_ble_peer_count",expected)
      .put("logical_strategy",BleAcquisitionPolicy.currentStrategy().name)
      .put("scan_filter_mode","MANUFACTURER_FILTERED")
      .put("hardware_filter_count",if(BleAcquisitionPolicy.currentStrategy()==BleAcquisitionStrategy.UNFILTERED_RECOVERY) 0 else 1)
      .put("location_service_enabled",locationServiceEnabled(ctx) ?: JSONObject.NULL)
      .put("issues",JSONArray(issues))
  }

  private fun validationRunDiagnostics(ctx: Context, now: Long = System.currentTimeMillis()): JSONObject {
    if (ValidationRuntime.runId != null && ValidationRuntime.endedWallMs == null) {
      ValidationRuntime.recordEnvironmentViolation(now, validationEnvironmentIssues(ctx))
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
      .put("schema_version",14)
      .put("release","dev-12")
      .put("build","0.2.0-experimental.12")
      .put("protocol_version",2)
      .put("device",deviceReport(ctx))
      .put("preflight",preflightDiagnostics(ctx,now))
      .put("release_truth",JSONObject()
        .put("profile_id","android-ble-lab-v1").put("rssi_at_1m_dbm",-69.19).put("path_loss_exponent",3.62)
        .put("min_samples_for_range",3).put("fresh_ms",5000).put("holdover_max_ms",10000).put("hard_expiry_ms",10000)
        .put("valid_distance_min_m",0.5).put("valid_distance_max_m",5.0).put("primary_acquisition","FILTERED_PRIMARY")
        .put("recovery_acquisition","UNFILTERED_RECOVERY").put("restart_cooldown_ms",30000).put("max_recoveries_per_5min",3)
        .put("physical_confidence","COARSE"))
      .put("safety_truth",JSONObject().put("human_scanning_enabled",false).put("human_localization_validated",false).put("rescue_use_validated",false))
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
    put("ranges", rangeObservations())
    put("manual_geometry_override", false)
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

  private fun expirePeers(now: Long) {
    val expired = FabricRuntime.peers.entries
      .filter { now - it.value.second > PEER_EXPIRY_MS }
      .map { it.key }
    for (nodeId in expired) {
      if (FabricRuntime.peers.remove(nodeId) != null) {
        FabricRuntime.peerExpireCount.incrementAndGet()
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
            ValidationRuntime.recordEnvironmentViolation(now, validationEnvironmentIssues(ctx))
          }
          if (Build.VERSION.SDK_INT >= 36 && now >= nextSystemRangingRefresh && hasPermission(ctx, RANGE_PERMISSION)) {
            try { SystemRangingApi36.refresh(ctx, desiredSystemRangingPeers()) } catch (_: Throwable) {}
            nextSystemRangingRefresh = now + 1_000L
          }
          if (now >= nextSend) {
            val bytes = advertisement(ctx).toString().toByteArray(Charsets.UTF_8)
            try {
              socket.send(DatagramPacket(bytes, bytes.size, groupAddress, PORT))
              FabricRuntime.txPackets.incrementAndGet()
            } catch (_: Throwable) {}
            try {
              socket.send(DatagramPacket(bytes, bytes.size, broadcastAddress, PORT))
              FabricRuntime.txPackets.incrementAndGet()
            } catch (_: Throwable) {}
            nextSend = now + 800L
          }
          try {
            val packet = DatagramPacket(buffer, buffer.size)
            socket.receive(packet)
            FabricRuntime.rxPackets.incrementAndGet()
            val text = String(packet.data, packet.offset, packet.length, Charsets.UTF_8)
            val obj = JSONObject(text)
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
              FabricRuntime.peers[remoteId] = text to seen
              FabricRuntime.peerLastSeenWallMs[remoteId] = seen
              FabricRuntime.peerPacketCounts.computeIfAbsent(remoteId) { AtomicLong(0) }.incrementAndGet()
            }
          } catch (_: java.net.SocketTimeoutException) {
          } catch (_: Throwable) {}
          expirePeers(now)
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
