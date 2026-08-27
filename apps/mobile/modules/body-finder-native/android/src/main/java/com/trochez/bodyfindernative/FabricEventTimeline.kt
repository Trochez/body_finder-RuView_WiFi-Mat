package com.trochez.bodyfindernative

import org.json.JSONArray
import org.json.JSONObject
import java.util.ArrayDeque

/**
 * Run-scoped, bounded causal timeline for UDP peer continuity.
 * It intentionally stores only diagnostics and never mutates acquisition/fabric policy.
 */
object FabricEventTimeline {
  private const val MAX_EVENTS = 256
  private val events = ArrayDeque<JSONObject>()
  private var runId: String? = null
  private var startedWallMs: Long? = null
  private var seq: Long = 0
  private var totalCount: Long = 0
  private var truncated: Boolean = false
  private var expectedPeerIdsAtStart: List<String> = emptyList()

  @Synchronized
  fun start(id: String, now: Long, expectedPeerIds: List<String>) {
    events.clear()
    runId = id
    startedWallMs = now
    seq = 0
    totalCount = 0
    truncated = false
    expectedPeerIdsAtStart = expectedPeerIds.distinct().sorted()
    record(
      "FABRIC_RUN_STARTED",
      JSONObject()
        .put("wall_ms", now)
        .put("expected_peer_ids_at_start", JSONArray(expectedPeerIdsAtStart))
        .put("expected_peer_count_at_start", expectedPeerIdsAtStart.size)
    )
  }

  @Synchronized
  fun record(type: String, details: JSONObject) {
    if (runId == null) return
    seq += 1
    totalCount += 1
    val now = details.optLong("wall_ms", System.currentTimeMillis())
    val event = JSONObject(details.toString())
      .put("seq", seq)
      .put("type", type)
      .put("run_id", runId)
      .put("elapsed_from_run_start_ms", startedWallMs?.let { (now - it).coerceAtLeast(0L) } ?: JSONObject.NULL)
    if (events.size >= MAX_EVENTS) {
      events.removeFirst()
      truncated = true
    }
    events.addLast(event)
  }

  @Synchronized
  fun snapshot(now: Long): JSONObject {
    val arr = JSONArray()
    events.forEach { arr.put(JSONObject(it.toString())) }
    return JSONObject()
      .put("run_id", runId ?: JSONObject.NULL)
      .put("started_wall_ms", startedWallMs ?: JSONObject.NULL)
      .put("snapshot_wall_ms", now)
      .put("expected_peer_ids_at_start", JSONArray(expectedPeerIdsAtStart))
      .put("expected_peer_count_at_start", expectedPeerIdsAtStart.size)
      .put("events", arr)
      .put("total_count", totalCount)
      .put("truncated", truncated)
      .put("capacity", MAX_EVENTS)
  }

  @Synchronized
  fun lossIntervals(now: Long): JSONArray {
    val starts = mutableMapOf<String, JSONObject>()
    val out = JSONArray()
    events.forEach { event ->
      val peer = event.optString("peer_id")
      if (peer.isBlank()) return@forEach
      when (event.optString("type")) {
        "PEER_BECAME_STALE", "PEER_EXPIRED" -> if (!starts.containsKey(peer)) starts[peer] = event
        "PEER_REACTIVATED" -> {
          val start = starts.remove(peer) ?: return@forEach
          out.put(JSONObject()
            .put("peer_id", peer)
            .put("started_wall_ms", start.optLong("wall_ms"))
            .put("ended_wall_ms", event.optLong("wall_ms"))
            .put("duration_ms", (event.optLong("wall_ms") - start.optLong("wall_ms")).coerceAtLeast(0L))
            .put("terminal_state", "REACTIVATED"))
        }
      }
    }
    starts.forEach { (peer, start) ->
      out.put(JSONObject()
        .put("peer_id", peer)
        .put("started_wall_ms", start.optLong("wall_ms"))
        .put("ended_wall_ms", JSONObject.NULL)
        .put("duration_ms", (now - start.optLong("wall_ms")).coerceAtLeast(0L))
        .put("terminal_state", "OPEN"))
    }
    return out
  }
}
