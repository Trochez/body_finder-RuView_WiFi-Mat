package com.trochez.bodyfindernative

import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.max

internal data class EnvironmentObservation(
  val appVisibility: String, val screenOn: Boolean, val batterySaver: Boolean,
  val foregroundServiceRunning: Boolean, val bleScannerRunning: Boolean,
  val strategy: String, val recoveryGeneration: Long?, val source: String,
)

internal object EnvironmentViolationTracker {
  private data class Open(val type: String, val started: Long, val observation: EnvironmentObservation)
  private val active = linkedMapOf<String, Open>()
  private val completed = mutableListOf<JSONObject>()
  private var firstWall: Long? = null
  private var visibilityTransitions = 0L
  private var totalBackgroundMs = 0L
  private var maxBackgroundMs = 0L
  private var lastVisibility: String? = null

  @Synchronized fun reset() { active.clear(); completed.clear(); firstWall=null; visibilityTransitions=0; totalBackgroundMs=0; maxBackgroundMs=0; lastVisibility=null }

  @Synchronized fun noteVisibility(now: Long, visibility: String) {
    val old = lastVisibility
    if (old != null && old != visibility) {
      visibilityTransitions++
      ValidationEventLog.record("APP_VISIBILITY_CHANGED", "$old->$visibility", now=now, authorizationReason="ACTIVITY_LIFECYCLE")
    }
    lastVisibility = visibility
  }

  private fun jsonFor(o: Open, resolved: Long?): JSONObject {
    val duration = max(0L, (resolved ?: System.currentTimeMillis()) - o.started)
    val x = o.observation
    return JSONObject()
      .put("type", o.type).put("started_wall_ms", o.started)
      .put("resolved_wall_ms", resolved ?: JSONObject.NULL).put("duration_ms", duration)
      .put("app_visibility_before", if (x.appVisibility == "active") "FOREGROUND" else "BACKGROUND")
      .put("app_visibility_after", if (resolved != null && o.type == "APP_NOT_FOREGROUND") "FOREGROUND" else if (x.appVisibility == "active") "FOREGROUND" else "BACKGROUND")
      .put("screen_state", if (x.screenOn) "ON" else "OFF").put("battery_saver", x.batterySaver)
      .put("foreground_service_state", if (x.foregroundServiceRunning) "RUNNING" else "STOPPED")
      .put("scan_state", if (x.bleScannerRunning) "ACTIVE" else "STOPPED")
      .put("acquisition_strategy", x.strategy).put("recovery_generation", x.recoveryGeneration ?: JSONObject.NULL)
      .put("source", if (o.type == "APP_NOT_FOREGROUND") "ACTIVITY_LIFECYCLE" else x.source)
      .put("confirmed", true).put("classification", if (resolved == null) "UNRESOLVED" else if (duration < 1000L) "TRANSIENT" else "SUSTAINED")
  }

  @Synchronized fun observe(now: Long, issues: List<String>, observation: EnvironmentObservation) {
    noteVisibility(now, observation.appVisibility)
    val current = issues.toSet()
    current.forEach { type -> if (!active.containsKey(type)) { active[type]=Open(type, now, observation); if (firstWall==null) firstWall=now } }
    val resolved = active.keys.filter { it !in current }
    resolved.forEach { type ->
      val o=active.remove(type) ?: return@forEach; val e=jsonFor(o, now); completed += e
      if (type == "APP_NOT_FOREGROUND") { val d=e.optLong("duration_ms"); totalBackgroundMs += d; maxBackgroundMs=maxOf(maxBackgroundMs,d) }
    }
  }

  @Synchronized fun count(): Long = (completed.size + active.size).toLong()
  @Synchronized fun firstWallMs(): Long? = firstWall
  @Synchronized fun types(): List<String> = (completed.map { it.optString("type") } + active.keys).filter { it.isNotBlank() }.distinct()
  @Synchronized fun snapshot(now: Long): JSONObject {
    val arr=JSONArray(); completed.forEach { arr.put(JSONObject(it.toString())) }
    var total=totalBackgroundMs; var maxBg=maxBackgroundMs
    active.values.forEach { o -> val e=jsonFor(o, null); e.put("duration_ms", max(0L, now-o.started)); arr.put(e); if(o.type=="APP_NOT_FOREGROUND") { val d=max(0L,now-o.started); total+=d; maxBg=maxOf(maxBg,d) } }
    return JSONObject().put("events", arr).put("violation_count", count()).put("first_violation_wall_ms", firstWall ?: JSONObject.NULL)
      .put("violation_types", JSONArray(types())).put("total_background_ms", total).put("max_background_interval_ms", maxBg)
      .put("foreground_transition_count", visibilityTransitions).put("unresolved_violation_count", active.size)
  }
}
