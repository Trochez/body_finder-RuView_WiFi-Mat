package com.trochez.bodyfindernative

import android.bluetooth.le.BluetoothLeScanner
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanSettings
import android.os.Build
import org.json.JSONObject
import java.util.concurrent.ConcurrentLinkedDeque
import java.util.concurrent.atomic.AtomicLong
import kotlin.math.max

/**
 * Acquisition-only policy for experimental.8.
 *
 * This object MUST NOT change metric calibration, sample-count requirements,
 * freshness, holdover, or solver rules. Its job is to make Android deliver
 * Body Finder advertisements to the already-validated estimator as regularly
 * as possible and to expose enough timing evidence to diagnose every pair.
 */
internal object BleAcquisitionPolicy {
  const val SCAN_STRATEGY = "LOW_LATENCY_SOFTWARE_FILTERED_ALL_MATCHES"
  const val REPORT_DELAY_MS = 0L
  const val MAX_INTERVAL_SAMPLES = 128
  const val GAP_1S_MS = 1_000L
  const val GAP_2S_MS = 2_000L
  const val GAP_5S_MS = 5_000L
  const val GAP_10S_MS = 10_000L
  const val SYSTEM_RANGING_BLE_YIELD_MS = 120_000L
  const val SYSTEM_RANGING_CLOSES_BEFORE_YIELD = 6L

  fun scanSettings(): ScanSettings {
    val builder = ScanSettings.Builder()
      .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
      .setReportDelay(REPORT_DELAY_MS)
      .setCallbackType(ScanSettings.CALLBACK_TYPE_ALL_MATCHES)
    if (Build.VERSION.SDK_INT >= 23) {
      builder
        .setMatchMode(ScanSettings.MATCH_MODE_AGGRESSIVE)
        .setNumOfMatches(ScanSettings.MATCH_NUM_MAX_ADVERTISEMENT)
    }
    return builder.build()
  }

  /**
   * Deliberately use no controller/hardware ScanFilter. Body Finder's
   * manufacturer id and payload magic are validated in recordScan(). This
   * avoids device-specific hardware/offload filter suppression while keeping
   * exactly the same logical Body Finder filter.
   */
  fun startSoftwareFilteredScan(scanner: BluetoothLeScanner, callback: ScanCallback) {
    scanner.startScan(null, scanSettings(), callback)
  }

  fun matchModeLabel(): String = if (Build.VERSION.SDK_INT >= 23) "AGGRESSIVE" else "PLATFORM_DEFAULT"
  fun numMatchesLabel(): String = if (Build.VERSION.SDK_INT >= 23) "MAX_ADVERTISEMENT" else "PLATFORM_DEFAULT"

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
)

internal class BleAcquisitionStats {
  private val firstCallbackWallMs = AtomicLong(0)
  private val lastCallbackWallMs = AtomicLong(0)
  private val callbackCount = AtomicLong(0)
  private val validCallbackCount = AtomicLong(0)
  private val invalidCallbackCount = AtomicLong(0)
  private val intervalCount = AtomicLong(0)
  private val intervalSumMs = AtomicLong(0)
  private val maxIntervalMs = AtomicLong(0)
  private val gapGt1sCount = AtomicLong(0)
  private val gapGt2sCount = AtomicLong(0)
  private val gapGt5sCount = AtomicLong(0)
  private val gapGt10sCount = AtomicLong(0)
  private val recentIntervalsMs = ConcurrentLinkedDeque<Long>()

  fun record(now: Long, validRssi: Boolean) {
    firstCallbackWallMs.compareAndSet(0L, now)
    val previous = lastCallbackWallMs.getAndSet(now)
    callbackCount.incrementAndGet()
    if (validRssi) validCallbackCount.incrementAndGet() else invalidCallbackCount.incrementAndGet()
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

  fun snapshot(): BleAcquisitionCounterSnapshot = BleAcquisitionCounterSnapshot(
    callbackCount = callbackCount.get(),
    validCallbackCount = validCallbackCount.get(),
    invalidCallbackCount = invalidCallbackCount.get(),
    gapGt1sCount = gapGt1sCount.get(),
    gapGt2sCount = gapGt2sCount.get(),
    gapGt5sCount = gapGt5sCount.get(),
    gapGt10sCount = gapGt10sCount.get(),
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
    fun delta(current: Long, previous: Long?): Long = (current - (previous ?: current)).coerceAtLeast(0L)
    return JSONObject()
      .put("acquisition_health", BleAcquisitionPolicy.health(snap.callbackCount, currentGap, valid5s, valid8s))
      .put("first_callback_wall_ms", first ?: JSONObject.NULL)
      .put("last_callback_wall_ms", last ?: JSONObject.NULL)
      .put("current_gap_ms", currentGap ?: JSONObject.NULL)
      .put("callback_count", snap.callbackCount)
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
      .put("run_callback_delta", delta(snap.callbackCount, baseline?.callbackCount))
      .put("run_valid_callback_delta", delta(snap.validCallbackCount, baseline?.validCallbackCount))
      .put("run_invalid_callback_delta", delta(snap.invalidCallbackCount, baseline?.invalidCallbackCount))
      .put("run_gap_gt_1s_delta", delta(snap.gapGt1sCount, baseline?.gapGt1sCount))
      .put("run_gap_gt_2s_delta", delta(snap.gapGt2sCount, baseline?.gapGt2sCount))
      .put("run_gap_gt_5s_delta", delta(snap.gapGt5sCount, baseline?.gapGt5sCount))
      .put("run_gap_gt_10s_delta", delta(snap.gapGt10sCount, baseline?.gapGt10sCount))
  }
}
