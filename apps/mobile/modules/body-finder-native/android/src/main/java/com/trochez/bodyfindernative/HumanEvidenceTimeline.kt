package com.trochez.bodyfindernative

import android.os.SystemClock
import org.json.JSONArray
import org.json.JSONObject
import java.util.ArrayDeque
import java.util.concurrent.atomic.AtomicLong

/** Bounded validation-run-scoped BLE RSSI evidence. Ground truth never enters runtime inference. */
internal object HumanEvidenceTimeline {
  private const val MAX_SAMPLES = 12_000
  private val seq = AtomicLong(0)
  private val samples = ArrayDeque<JSONObject>()
  private var runId: String? = null
  private var startedWallMs: Long? = null
  private var endedWallMs: Long? = null
  private var dropped: Long = 0

  @Synchronized fun start(id: String, now: Long) { runId=id; startedWallMs=now; endedWallMs=null; dropped=0; seq.set(0); samples.clear() }

  @Synchronized fun recordBle(observerNodeId: String, peerBleIdentity: String, rssi: Int, txPower: Int, now: Long) {
    if (runId == null || endedWallMs != null || rssi !in -126..0 || peerBleIdentity.isBlank()) return
    while (samples.size >= MAX_SAMPLES) { samples.removeFirst(); dropped++ }
    samples.addLast(JSONObject().put("seq",seq.incrementAndGet()).put("wall_ms",now).put("monotonic_ns",SystemClock.elapsedRealtimeNanos())
      .put("observer_node_id",observerNodeId).put("peer_ble_identity",peerBleIdentity).put("modality","BLE_RSSI_DBM").put("rssi_dbm",rssi)
      .put("tx_power_dbm",if (txPower in -100..20) txPower else JSONObject.NULL).put("provenance","ANDROID_BLE_SCAN_CALLBACK_REAL"))
  }

  @Synchronized fun end(now: Long) { if (runId != null && endedWallMs == null) endedWallMs=now }

  @Synchronized fun snapshot(now: Long): JSONObject = JSONObject().put("schema_version",1).put("run_id",runId ?: JSONObject.NULL)
    .put("active",runId != null && endedWallMs == null).put("started_wall_ms",startedWallMs ?: JSONObject.NULL).put("ended_wall_ms",endedWallMs ?: JSONObject.NULL)
    .put("captured_wall_ms",now).put("screenshots_required",false).put("ground_truth_in_runtime",false).put("dropped_sample_count",dropped)
    .put("sample_count",samples.size).put("samples",JSONArray(samples.toList()))
}
