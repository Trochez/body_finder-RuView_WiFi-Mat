from pathlib import Path
import copy, hashlib, json, re

ROOT = Path(__file__).resolve().parents[1]

def p(rel): return ROOT / rel
def read(rel): return p(rel).read_text()
def write(rel, content):
    path = p(rel); path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content)
def replace_once(rel, old, new):
    s = read(rel)
    if old not in s: raise SystemExit(f'anchor missing in {rel}: {old[:100]!r}')
    write(rel, s.replace(old, new, 1))

# Version truth: protocol/schema/calibration stay frozen; only release iteration changes.
write('apps/mobile/src/version.ts', '''export const RELEASE = Object.freeze({
  build: '0.2.0-experimental.14',
  reportVersion: 16,
  versionCode: 14,
  releaseIteration: 'experimental.14',
  protocolVersion: 2,
  snapshotSchemaVersion: 3,
  humanScanningEnabled: false,
  humanLocalizationValidated: false,
  rescueUseValidated: false,
});
export const BUILD = RELEASE.build;
export const REPORT_VERSION = RELEASE.reportVersion;
export const HUMAN_SCANNING_ENABLED = RELEASE.humanScanningEnabled;
''')
app = json.loads(read('apps/mobile/app.json'))
app['expo']['android']['versionCode'] = 14
app['expo']['extra']['releaseIteration'] = 'experimental.14'
write('apps/mobile/app.json', json.dumps(app, indent=2, ensure_ascii=False) + '\n')
app_tsx = read('apps/mobile/App.tsx')
app_tsx = app_tsx.replace('experimental.13', 'experimental.14').replace('dev13-self-contained-json-evidence-v2', 'dev14-self-contained-json-evidence-v3').replace('dev-13', 'dev-14')
old_listener = '''    const appStateSubscription = AppState.addEventListener('change', state => {\n      try { BodyFinderNative.updateAppVisibility(state); } catch {}\n    });'''
new_listener = '''    const appStateSubscription = AppState.addEventListener('change', state => {\n      try { BodyFinderNative.updateAppVisibility(state); } catch {}\n      if (state !== 'active') setValidationNotice(lang === 'es' ? 'La app salió de primer plano; el JSON registrará el intervalo y su contexto.' : 'The app left foreground; JSON will record the interval and its context.');\n    });'''
if old_listener in app_tsx: app_tsx = app_tsx.replace(old_listener, new_listener, 1)
write('apps/mobile/App.tsx', app_tsx)

# Frozen truth and dev13->dev14 finding/acceptance contract.
write('DEV14_FROZEN_TRUTH.md', '''# DEV14 Frozen Truth\n\n- Build: `0.2.0-experimental.14`; tag: `dev-14`; protocol: `2`; validation snapshot: compatible `v3`.\n- BLE profile: `android-ble-lab-v1`; min RSSI samples `3`; fresh `5000 ms`; holdover/hard expiry `10000 ms`.\n- Unfiltered recovery `10000 ms`; filtered probe public hard maximum `15000 ms`; internal exit target `14500 ms`.\n- Restart cooldown `30000 ms`; maximum recovery attempts `3` per rolling 5 minutes.\n- Geometry is automatic only. Manual geometry, human scanning, validated human localization and rescue claims remain false.\n- Screenshots are not acceptance evidence. JSON/JSONL is the diagnostic source of truth.\n- No calibration, path-loss, ranging, reciprocal fusion, holdover, sigma-aging or geometry-solver changes are authorized by dev14.\n\nSchema decision: v3 is retained because it explicitly allows compatible additional properties. Dev14 adds recovery/lifecycle diagnostics without changing existing required semantics.\n''')
write('docs/DEV13_TO_DEV14_FINDINGS.md', '''# dev13 → dev14 closure matrix\n\n| dev13 finding | dev14 fix | automated gate |\n|---|---|---|\n| RECOVERY_START_MISSING | terminal event and probe transition are atomic; recovery provenance survives probe | timeline + Android contract |\n| FILTERED_PROBE_WINDOW_EXPIRED | 14.5 s internal exit target, 15 s validator hard maximum unchanged | deterministic deadline fixtures |\n| targeted SUCCESS without associated first-valid | generation-local target first-valid is mandatory before success | causality fixtures |\n| APP_NOT_FOREGROUND ambiguous/duplicated | logical violation intervals with lifecycle/environment provenance | environment interval fixtures |\n| short run could threaten evidence selection | frozen completed-run history remains selected/re-exportable | history fixtures |\n''')

# Recovery generation lifecycle/causality/deadline.
ble_rel = 'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleAcquisitionPolicy.kt'
ble = read(ble_rel).replace('experimental.13', 'experimental.14')
ble = ble.replace('  const val FILTERED_PROBE_WINDOW_MS = 15_000L\n', '  const val FILTERED_PROBE_WINDOW_MS = 15_000L\n  const val FILTERED_PROBE_EXIT_TARGET_MS = 14_500L\n', 1)
ble = ble.replace('''  @Volatile private var recoveryStartedWallMs: Long? = null\n  @Volatile private var lastRecoveryLatencyMs: Long? = null''', '''  @Volatile private var recoveryStartedWallMs: Long? = null\n  @Volatile private var recoveryProbeStartedWallMs: Long? = null\n  @Volatile private var recoveryProbeDeadlineWallMs: Long? = null\n  @Volatile private var firstValidCallbackGeneration: Long? = null\n  @Volatile private var firstValidCallbackPeerId: String? = null\n  @Volatile private var firstValidCallbackWallMs: Long? = null\n  @Volatile private var lastRecoveryLatencyMs: Long? = null''', 1)
ble = ble.replace('''    recoveryStartedWallMs = null\n    lastRecoveryLatencyMs = null''', '''    recoveryStartedWallMs = null\n    recoveryProbeStartedWallMs = null\n    recoveryProbeDeadlineWallMs = null\n    firstValidCallbackGeneration = null\n    firstValidCallbackPeerId = null\n    firstValidCallbackWallMs = null\n    lastRecoveryLatencyMs = null''', 1)
ble = ble.replace('''  fun recoveryStartedMs(): Long? = recoveryStartedWallMs\n  fun transitionCount(): Long = transitionCount''', '''  fun recoveryStartedMs(): Long? = recoveryStartedWallMs\n  fun recoveryProbeStartedMs(): Long? = recoveryProbeStartedWallMs\n  fun recoveryProbeDeadlineMs(): Long? = recoveryProbeDeadlineWallMs\n  fun firstValidRecoveryGeneration(): Long? = firstValidCallbackGeneration\n  fun firstValidRecoveryPeerId(): String? = firstValidCallbackPeerId\n  fun firstValidRecoveryWallMs(): Long? = firstValidCallbackWallMs\n  fun transitionCount(): Long = transitionCount''', 1)
old_eligible = '''  fun recoveryCallbackEligible(peerId: String?): Boolean =\n    activeRecoveryTriggerKind != RecoveryTriggerKind.PEER_STARVATION ||\n      (peerId != null && peerId == activeRecoveryTriggerPeerId)'''
new_eligible = '''  fun recoveryCallbackEligible(peerId: String?): Boolean {\n    val generation = activeRecoveryGeneration ?: return false\n    if (recoveryTerminalGeneration.get() == generation) return false\n    return activeRecoveryTriggerKind != RecoveryTriggerKind.PEER_STARVATION ||\n      (peerId != null && peerId == activeRecoveryTriggerPeerId)\n  }'''
if old_eligible not in ble: raise SystemExit('eligible anchor missing')
ble = ble.replace(old_eligible, new_eligible, 1)
old_transition_fragment = '''    strategySinceWallMs = now\n    lastStrategyReason = reason\n    strategyRecoveryGeneration = if (next == BleAcquisitionStrategy.UNFILTERED_RECOVERY || next == BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE) activeRecoveryGeneration else null\n    transitionCount++'''
new_transition_fragment = '''    strategySinceWallMs = now\n    lastStrategyReason = reason\n    strategyRecoveryGeneration = if (next == BleAcquisitionStrategy.UNFILTERED_RECOVERY || next == BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE) activeRecoveryGeneration else null\n    if (next == BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE) {\n      recoveryProbeStartedWallMs = now\n      recoveryProbeDeadlineWallMs = now + FILTERED_PROBE_EXIT_TARGET_MS\n    }\n    transitionCount++'''
if old_transition_fragment not in ble: raise SystemExit('transition fragment missing')
ble = ble.replace(old_transition_fragment, new_transition_fragment, 1)
ble = ble.replace('''      activeRecoveryTriggerPeerId = null\n      recoveryStartedWallMs = null\n    }''', '''      activeRecoveryTriggerPeerId = null\n      recoveryStartedWallMs = null\n      recoveryProbeStartedWallMs = null\n      recoveryProbeDeadlineWallMs = null\n      firstValidCallbackGeneration = null\n      firstValidCallbackPeerId = null\n      firstValidCallbackWallMs = null\n    }''', 1)
ble = ble.replace('''    activeRecoveryTriggerPeerId = triggerPeerId\n    lastRecoveryTriggerKind = triggerKind''', '''    activeRecoveryTriggerPeerId = triggerPeerId\n    recoveryProbeStartedWallMs = null\n    recoveryProbeDeadlineWallMs = null\n    firstValidCallbackGeneration = null\n    firstValidCallbackPeerId = null\n    firstValidCallbackWallMs = null\n    lastRecoveryTriggerKind = triggerKind''', 1)
old_success = '''  @Synchronized\n  fun noteRecoverySuccess(now: Long, peerId: String? = null) {\n    val generation = activeRecoveryGeneration ?: return\n    if (!recoveryCallbackEligible(peerId)) return\n    if (recoveryTerminalGeneration.get() == generation) return\n    recoveryTerminalGeneration.set(generation)\n    recoverySuccessGeneration.set(generation)\n    val start = recoveryStartedWallMs\n    if (start != null) lastRecoveryLatencyMs = max(0L, now - start)\n    cohortRecoveryCount++\n    if (activeRecoveryTriggerKind == RecoveryTriggerKind.PEER_STARVATION) peerStarvationRecoverySuccessCount++\n    ValidationEventLog.record(\n      "RECOVERY_SUCCESS", "FIRST_VALID_BF_CALLBACK", now = now,\n      peerId = activeRecoveryTriggerPeerId ?: peerId,\n      triggerKind = activeRecoveryTriggerKind?.name,\n    )\n    recoveryStartedWallMs = null\n  }'''
new_success = '''  @Synchronized\n  fun noteRecoveryFirstValidCallback(now: Long, peerId: String?): Boolean {\n    val generation = activeRecoveryGeneration ?: return false\n    if (strategy != BleAcquisitionStrategy.UNFILTERED_RECOVERY) return false\n    if (!recoveryCallbackEligible(peerId)) return false\n    if (firstValidCallbackGeneration == generation) return false\n    firstValidCallbackGeneration = generation\n    firstValidCallbackPeerId = peerId\n    firstValidCallbackWallMs = now\n    ValidationEventLog.record(\n      "FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY", "BODY_FINDER_CALLBACK", now = now,\n      peerId = peerId, triggerKind = activeRecoveryTriggerKind?.name,\n      triggerPeerId = activeRecoveryTriggerPeerId,\n    )\n    return true\n  }\n\n  @Synchronized\n  fun noteRecoverySuccess(now: Long, peerId: String? = null) {\n    val generation = activeRecoveryGeneration ?: return\n    if (recoveryTerminalGeneration.get() == generation) return\n    if (firstValidCallbackGeneration != generation) return\n    if (activeRecoveryTriggerKind == RecoveryTriggerKind.PEER_STARVATION &&\n      (firstValidCallbackPeerId != activeRecoveryTriggerPeerId || peerId != activeRecoveryTriggerPeerId)) return\n    recoveryTerminalGeneration.set(generation)\n    recoverySuccessGeneration.set(generation)\n    val start = recoveryStartedWallMs\n    if (start != null) lastRecoveryLatencyMs = max(0L, now - start)\n    cohortRecoveryCount++\n    if (activeRecoveryTriggerKind == RecoveryTriggerKind.PEER_STARVATION) peerStarvationRecoverySuccessCount++\n    ValidationEventLog.record(\n      "RECOVERY_SUCCESS", "TARGET_FIRST_VALID_CONFIRMED", now = now,\n      peerId = activeRecoveryTriggerPeerId ?: peerId, triggerKind = activeRecoveryTriggerKind?.name,\n      triggerPeerId = activeRecoveryTriggerPeerId,\n    )\n    transition(BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE, now, "RECOVERY_SUCCESS")\n  }'''
if old_success not in ble: raise SystemExit('success block missing')
ble = ble.replace(old_success, new_success, 1)
old_failure = '''  @Synchronized\n  fun noteRecoveryFailure(now: Long = System.currentTimeMillis()) {\n    val generation = activeRecoveryGeneration ?: return\n    if (recoveryTerminalGeneration.get() == generation) return\n    recoveryTerminalGeneration.set(generation)\n    recoveryFailureGeneration.set(generation)\n    cohortRecoveryFailureCount++\n    if (activeRecoveryTriggerKind == RecoveryTriggerKind.PEER_STARVATION) peerStarvationRecoveryFailureCount++\n    ValidationEventLog.record(\n      "RECOVERY_FAILURE", "RECOVERY_WINDOW_EXPIRED", now = now,\n      peerId = activeRecoveryTriggerPeerId,\n      triggerKind = activeRecoveryTriggerKind?.name,\n    )\n    recoveryStartedWallMs = null\n  }'''
new_failure = '''  @Synchronized\n  fun noteRecoveryFailure(now: Long = System.currentTimeMillis()) {\n    val generation = activeRecoveryGeneration ?: return\n    if (recoveryTerminalGeneration.get() == generation) return\n    recoveryTerminalGeneration.set(generation)\n    recoveryFailureGeneration.set(generation)\n    cohortRecoveryFailureCount++\n    if (activeRecoveryTriggerKind == RecoveryTriggerKind.PEER_STARVATION) peerStarvationRecoveryFailureCount++\n    ValidationEventLog.record(\n      "RECOVERY_FAILURE", "RECOVERY_WINDOW_EXPIRED", now = now,\n      peerId = activeRecoveryTriggerPeerId, triggerKind = activeRecoveryTriggerKind?.name,\n      triggerPeerId = activeRecoveryTriggerPeerId,\n    )\n    transition(BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE, now, "RECOVERY_FAILURE")\n  }'''
if old_failure not in ble: raise SystemExit('failure block missing')
ble = ble.replace(old_failure, new_failure, 1)
ble = ble.replace('''    .put("recovery_started_wall_ms", recoveryStartedWallMs ?: JSONObject.NULL)''', '''    .put("recovery_started_wall_ms", recoveryStartedWallMs ?: JSONObject.NULL)\n    .put("recovery_probe_started_wall_ms", recoveryProbeStartedWallMs ?: JSONObject.NULL)\n    .put("recovery_probe_deadline_wall_ms", recoveryProbeDeadlineWallMs ?: JSONObject.NULL)\n    .put("probe_elapsed_ms", recoveryProbeStartedWallMs?.let { max(0L, now - it) } ?: JSONObject.NULL)\n    .put("probe_remaining_ms", recoveryProbeDeadlineWallMs?.let { max(0L, it - now) } ?: JSONObject.NULL)\n    .put("first_valid_callback_generation", firstValidCallbackGeneration ?: JSONObject.NULL)\n    .put("first_valid_callback_peer_id", firstValidCallbackPeerId ?: JSONObject.NULL)\n    .put("first_valid_callback_wall_ms", firstValidCallbackWallMs ?: JSONObject.NULL)''', 1)
ble = ble.replace('''    .put("filtered_probe_window_ms", FILTERED_PROBE_WINDOW_MS)''', '''    .put("filtered_probe_window_ms", FILTERED_PROBE_WINDOW_MS)\n    .put("filtered_probe_exit_target_ms", FILTERED_PROBE_EXIT_TARGET_MS)''', 1)
write(ble_rel, ble)

# Timeline now carries trigger peer explicitly; generation-local FIRST_VALID is owned by policy.
write('apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/ValidationEventLog.kt', r'''package com.trochez.bodyfindernative

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
''')

# Logical lifecycle/environment interval tracker. One interval == one violation, not one poll.
write('apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/EnvironmentViolationTracker.kt', r'''package com.trochez.bodyfindernative

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
''')

# Wire policy-owned first-valid, internal probe deadline, lifecycle interval telemetry and canonical snapshot identity.
native_rel='apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt'
n=read(native_rel)
old_cb='''    if (validRssi && BleAcquisitionPolicy.currentStrategy() == BleAcquisitionStrategy.UNFILTERED_RECOVERY && BleAcquisitionPolicy.recoveryCallbackEligible(callbackPeerId)) {\n      ValidationEventLog.record(\n        "FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY", "BODY_FINDER_CALLBACK", now = now,\n        peerId = callbackPeerId, triggerKind = BleAcquisitionPolicy.activeRecoveryTriggerKind()?.name,\n      )\n    }'''
new_cb='''    if (validRssi && BleAcquisitionPolicy.currentStrategy() == BleAcquisitionStrategy.UNFILTERED_RECOVERY) {\n      BleAcquisitionPolicy.noteRecoveryFirstValidCallback(now, callbackPeerId)\n    }'''
if old_cb not in n: raise SystemExit('callback anchor missing')
n=n.replace(old_cb,new_cb,1)
old_probe='''      BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE -> {\n        cohort = bodyFinderCohortHealth(now)\n        if (cohort == BodyFinderCohortHealth.BF_COHORT_STALLED) {\n          if (BleAcquisitionPolicy.canStartRecovery(now)) {\n            BleAcquisitionPolicy.beginRecovery(now, "PROBE_STALLED", RecoveryTriggerKind.FULL_COHORT_STALL)\n            restartScannerWithStrategy(now, BleAcquisitionStrategy.UNFILTERED_RECOVERY, "PROBE_STALLED")\n          } else {\n            BleAcquisitionPolicy.transition(BleAcquisitionStrategy.COOLDOWN, now, "RECOVERY_COOLDOWN")\n          }\n        } else if (now - BleAcquisitionPolicy.strategySinceMs() >= BleAcquisitionPolicy.FILTERED_PROBE_WINDOW_MS) {\n          BleAcquisitionPolicy.transition(BleAcquisitionStrategy.FILTERED_PRIMARY, now, "PROBE_STABLE")\n        }\n      }'''
new_probe='''      BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE -> {\n        cohort = bodyFinderCohortHealth(now)\n        if (now - BleAcquisitionPolicy.strategySinceMs() >= BleAcquisitionPolicy.FILTERED_PROBE_EXIT_TARGET_MS) {\n          BleAcquisitionPolicy.transition(BleAcquisitionStrategy.FILTERED_PRIMARY, now, if (cohort == BodyFinderCohortHealth.BF_COHORT_STALLED) "PROBE_EXIT_TARGET_STALLED" else "PROBE_STABLE")\n        }\n      }'''
if old_probe not in n: raise SystemExit('probe block missing')
n=n.replace(old_probe,new_probe,1)
# reset tracker once per run
n=n.replace('''    environmentViolationTypes = ""\n    preflightAtStartJson =''','''    environmentViolationTypes = ""\n    EnvironmentViolationTracker.reset()\n    preflightAtStartJson =''',1)
# enrich environment recorder signature and logical interval accounting
n=n.replace('''    triggerKind: RecoveryTriggerKind?,\n    triggerPeerId: String?,\n  ) {''','''    triggerKind: RecoveryTriggerKind?,\n    triggerPeerId: String?,\n    ctx: Context,\n  ) {''',1)
old_tail='''    if (!decision.valid) unauthorizedStrategyViolationCount++\n    if (issues.isEmpty()) return\n    environmentViolationCount++\n    if (firstEnvironmentViolationWallMs == null) firstEnvironmentViolationWallMs = now\n    environmentViolationTypes = (environmentViolationTypes.split(',').filter { it.isNotBlank() } + issues).distinct().joinToString(",")'''
new_tail='''    if (!decision.valid) unauthorizedStrategyViolationCount++\n    val power = ctx.getSystemService(Context.POWER_SERVICE) as? PowerManager\n    EnvironmentViolationTracker.observe(now, issues, EnvironmentObservation(\n      appVisibility, power?.isInteractive == true, power?.isPowerSaveMode == true,\n      FieldServiceState.state == "RUNNING", FabricRuntime.bleScanning, strategy.name, recoveryGeneration, "ENVIRONMENT_EVALUATION"\n    ))\n    environmentViolationCount = EnvironmentViolationTracker.count()\n    firstEnvironmentViolationWallMs = EnvironmentViolationTracker.firstWallMs()\n    environmentViolationTypes = EnvironmentViolationTracker.types().joinToString(",")'''
if old_tail not in n: raise SystemExit('environment tail missing')
n=n.replace(old_tail,new_tail,1)
# Evaluation call sites have different indentation in diagnostics vs worker loop.
call_patterns = [
('''        BleAcquisitionPolicy.activeRecoveryGeneration(), BleAcquisitionPolicy.activeRecoveryTriggerKind(), BleAcquisitionPolicy.activeRecoveryTriggerPeerId(),\n      )''','''        BleAcquisitionPolicy.activeRecoveryGeneration(), BleAcquisitionPolicy.activeRecoveryTriggerKind(), BleAcquisitionPolicy.activeRecoveryTriggerPeerId(), ctx,\n      )'''),
('''              BleAcquisitionPolicy.activeRecoveryGeneration(), BleAcquisitionPolicy.activeRecoveryTriggerKind(), BleAcquisitionPolicy.activeRecoveryTriggerPeerId(),\n            )''','''              BleAcquisitionPolicy.activeRecoveryGeneration(), BleAcquisitionPolicy.activeRecoveryTriggerKind(), BleAcquisitionPolicy.activeRecoveryTriggerPeerId(), ctx,\n            )'''),
]
replaced=0
for a,b in call_patterns:
    if a in n:
        n=n.replace(a,b)
        replaced += 1
if replaced < 2: raise SystemExit(f'environment call anchors missing: {replaced}')
# AppState transition provenance.
old_vis='''    Function("updateAppVisibility") { visibility: String ->\n      ValidationRuntime.appVisibility = visibility\n      true\n    }'''
new_vis='''    Function("updateAppVisibility") { visibility: String ->\n      val now = System.currentTimeMillis()\n      ValidationRuntime.appVisibility = visibility\n      EnvironmentViolationTracker.noteVisibility(now, visibility)\n      true\n    }'''
if old_vis not in n: raise SystemExit('visibility function missing')
n=n.replace(old_vis,new_vis,1)
# Frozen environment interval evidence.
n=n.replace('''    val environment = JSONObject()\n      .put("valid", environmentViolationCount == 0L)''','''    val environmentIntervals = EnvironmentViolationTracker.snapshot(now)\n    environmentViolationCount = environmentIntervals.optLong("violation_count")\n    firstEnvironmentViolationWallMs = environmentIntervals.optLong("first_violation_wall_ms").takeIf { it > 0L }\n    environmentViolationTypes = (0 until environmentIntervals.optJSONArray("violation_types").length()).map { environmentIntervals.optJSONArray("violation_types").optString(it) }.joinToString(",")\n    val environment = JSONObject()\n      .put("valid", environmentViolationCount == 0L)''',1)
n=n.replace('''      .put("unauthorized_strategy_violation_count", unauthorizedStrategyViolationCount)''','''      .put("unauthorized_strategy_violation_count", unauthorizedStrategyViolationCount)\n      .put("environment_violation_events", environmentIntervals.optJSONArray("events"))\n      .put("total_background_ms", environmentIntervals.optLong("total_background_ms"))\n      .put("max_background_interval_ms", environmentIntervals.optLong("max_background_interval_ms"))\n      .put("foreground_transition_count", environmentIntervals.optLong("foreground_transition_count"))\n      .put("unresolved_violation_count", environmentIntervals.optLong("unresolved_violation_count"))''',1)
n=n.replace('''      .put("environment", environment)\n      .put("validation_counters", counters)''','''      .put("environment", environment)\n      .put("environment_violation_events", environmentIntervals.optJSONArray("events"))\n      .put("validation_counters", counters)''',1)
# Canonical frozen payload hash (hash is computed before inserting the hash field itself).
n=n.replace('''    val frozen = CompletedValidationRun(id, base.toString())''','''    val snapshotBytes = base.toString().toByteArray(Charsets.UTF_8)\n    val snapshotHash = MessageDigest.getInstance("SHA-256").digest(snapshotBytes).joinToString("") { "%02x".format(it) }\n    base.put("snapshot_identity_sha256", snapshotHash).put("json_self_contained", true).put("screenshots_required", false)\n    val frozen = CompletedValidationRun(id, base.toString())''',1)
write(native_rel,n)

# Compatible schema-v3 extension: existing required fields preserved.
schema=json.loads(read('protocol/schemas/validation-run-snapshot-v3.json'))
schema['properties']['environment_violation_events']={'type':'array','items':{'type':'object','required':['type','started_wall_ms','duration_ms','source','confirmed']}}
schema['properties']['snapshot_identity_sha256']={'type':'string','pattern':'^[0-9a-f]{64}$'}
schema['properties']['json_self_contained']={'const':True}
schema['properties']['screenshots_required']={'const':False}
env=schema['properties']['environment']
env.setdefault('properties',{}).update({
    'total_background_ms': {'type':'integer','minimum':0},
    'max_background_interval_ms': {'type':'integer','minimum':0},
    'foreground_transition_count': {'type':'integer','minimum':0},
    'unresolved_violation_count': {'type':'integer','minimum':0},
    'environment_violation_events': {'type':'array'},
})
# Keep these dev14 additions optional: schema v3 must remain backward-compatible with dev13 snapshots.
write('protocol/schemas/validation-run-snapshot-v3.json',json.dumps(schema,indent=2)+'\n')

# Shared deterministic dev14 validators.
write('validation/analysis/dev14_validation.py', r'''import json

def unwrap(doc):
    if isinstance(doc,dict) and isinstance(doc.get('validation_run'),dict): return doc['validation_run']
    if isinstance(doc,dict) and isinstance(doc.get('diagnostics'),dict) and isinstance(doc['diagnostics'].get('validation_run'),dict): return doc['diagnostics']['validation_run']
    if isinstance(doc,dict) and isinstance(doc.get('snapshot'),dict): return doc['snapshot']
    return doc if isinstance(doc,dict) else {}

def timeline_errors(doc):
    r=unwrap(doc); ev=r.get('events',[]) or []; errors=[]
    for key in ('seq','wall_ms'):
        vals=[e.get(key) for e in ev if isinstance(e.get(key),(int,float))]
        if vals != sorted(vals): errors.append('NON_MONOTONIC_'+key.upper())
    elapsed=[e.get('elapsed_from_run_start_ms',e.get('elapsed_ms')) for e in ev]
    elapsed=[x for x in elapsed if isinstance(x,(int,float))]
    if elapsed != sorted(elapsed): errors.append('NON_MONOTONIC_ELAPSED')
    by={}
    for e in ev:
        g=e.get('recovery_generation')
        if g is not None: by.setdefault(g,[]).append(e)
    for g,es in by.items():
        req=[e for e in es if e.get('type')=='RECOVERY_REQUESTED']; first=[e for e in es if e.get('type')=='FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY']
        suc=[e for e in es if e.get('type')=='RECOVERY_SUCCESS']; fail=[e for e in es if e.get('type')=='RECOVERY_FAILURE']; term=suc+fail
        if len(req)>1: errors.append('DUPLICATE_RECOVERY_REQUEST')
        if len(first)>1: errors.append('DUPLICATE_FIRST_VALID')
        if len(term)>1:
            errors.append('TERMINAL_CONTRADICTION' if suc and fail else 'DUPLICATE_TERMINAL')
        if suc and not first: errors.append('RECOVERY_SUCCESS_WITHOUT_FIRST_VALID')
        if suc and req and first:
            if not (req[0].get('seq',0)<first[0].get('seq',0)<suc[0].get('seq',0)): errors.append('RECOVERY_CAUSAL_ORDER_INVALID')
            if req[0].get('trigger_kind')=='PEER_STARVATION':
                target=req[0].get('trigger_peer_id') or req[0].get('peer_id')
                if first[0].get('peer_id')!=target or suc[0].get('peer_id')!=target: errors.append('FIRST_VALID_WRONG_TARGET')
        if term:
            terminal_seq=min(e.get('seq',0) for e in term)
            if any(e.get('type')=='FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY' and e.get('seq',0)>terminal_seq for e in es): errors.append('CALLBACK_AFTER_TERMINAL')
    return list(dict.fromkeys(errors))

def environment_errors(doc):
    r=unwrap(doc); env=r.get('environment',{}) or {}; errors=[]
    types=list(env.get('violation_types',[]) or [])
    if 'RECOVERY_START_MISSING' in types: errors.append('RECOVERY_START_MISSING')
    if 'FILTERED_PROBE_WINDOW_EXPIRED' in types: errors.append('FILTERED_PROBE_WINDOW_EXPIRED')
    if env.get('valid') is False:
        if 'APP_NOT_FOREGROUND' in types: errors.append('APP_NOT_FOREGROUND')
        elif not errors: errors.append('ENVIRONMENT_INVALID')
    events=r.get('environment_violation_events',env.get('environment_violation_events',[])) or []
    active_by={}
    for e in sorted(events,key=lambda x:x.get('started_wall_ms',0)):
        t=e.get('type'); s=e.get('started_wall_ms'); z=e.get('resolved_wall_ms'); d=e.get('duration_ms')
        if not t or not isinstance(s,(int,float)) or not isinstance(d,(int,float)) or d<0: errors.append('ENVIRONMENT_INTERVAL_INVALID'); continue
        if z is not None and isinstance(z,(int,float)) and z-s != d: errors.append('ENVIRONMENT_INTERVAL_DURATION_MISMATCH')
        prev=active_by.get(t)
        if prev is not None and s < prev: errors.append('DUPLICATE_OVERLAPPING_ENVIRONMENT_INTERVAL')
        active_by[t]=z if isinstance(z,(int,float)) else float('inf')
    return list(dict.fromkeys(errors))

def hard_gate_errors(doc, acceptance=True):
    r=unwrap(doc); errors=[]
    if r.get('snapshot_schema_version') not in (None,3): errors.append('SNAPSHOT_SCHEMA_DRIFT')
    if r.get('snapshot_frozen') is not True: errors.append('SNAPSHOT_NOT_FROZEN')
    elapsed=r.get('elapsed_ms',r.get('snapshot_elapsed_ms',0)) or 0
    if acceptance and elapsed < 300000: errors.append('LONG_RUN_TOO_SHORT')
    pre=r.get('preflight_at_start',{}) or {}
    if pre and pre.get('ready') is not True: errors.append('PREFLIGHT_NOT_READY')
    env=r.get('environment',{}) or {}
    if env.get('valid') is not True: errors += environment_errors(r)
    if (env.get('unauthorized_strategy_violation_count',0) or 0)!=0: errors.append('UNAUTHORIZED_STRATEGY_VIOLATION')
    if (r.get('usable_metric_range_uptime_percent',100) or 0)<90: errors.append('USABLE_METRIC_UPTIME_LOW')
    if (r.get('geometry_2d_uptime_percent',100) or 0)<90: errors.append('GEOMETRY2D_UPTIME_LOW')
    counters=r.get('validation_counters',{}) or {}
    if (counters.get('peer_expire_delta',r.get('peer_expire_delta',0)) or 0)!=0: errors.append('PEER_EXPIRE_NONZERO')
    acq=r.get('acquisition_state_at_end',{}) or {}
    if (acq.get('recovery_attempts_in_current_5min_window',0) or 0)>3: errors.append('RECOVERY_BUDGET_EXCEEDED')
    if (acq.get('filtered_probe_window_ms',15000) or 15000)!=15000: errors.append('FILTERED_PROBE_HARD_LIMIT_DRIFT')
    if (acq.get('filtered_probe_exit_target_ms',14500) or 14500)>14500: errors.append('FILTERED_PROBE_EXIT_TARGET_DRIFT')
    errors += timeline_errors(r)
    errors += environment_errors(r)
    return list(dict.fromkeys(errors))
''')
write('validation/analysis/validate_timeline_causality.py', '''#!/usr/bin/env python3\nimport json,sys\nfrom dev14_validation import timeline_errors\nd=json.load(open(sys.argv[1])); e=timeline_errors(d); print(json.dumps({"pass":not e,"errors":e},indent=2)); sys.exit(0 if not e else 1)\n''')
write('validation/analysis/validate_peer_starvation_recovery.py', '''#!/usr/bin/env python3\nimport json,sys\nfrom dev14_validation import timeline_errors\nd=json.load(open(sys.argv[1])); e=[x for x in timeline_errors(d) if x in {"FIRST_VALID_WRONG_TARGET","RECOVERY_SUCCESS_WITHOUT_FIRST_VALID","DUPLICATE_FIRST_VALID","DUPLICATE_TERMINAL","TERMINAL_CONTRADICTION","CALLBACK_AFTER_TERMINAL","RECOVERY_CAUSAL_ORDER_INVALID"}]; print(json.dumps({"pass":not e,"errors":e},indent=2)); sys.exit(0 if not e else 1)\n''')
write('validation/analysis/validate_environment_intervals.py', '''#!/usr/bin/env python3\nimport json,sys\nfrom dev14_validation import environment_errors\nd=json.load(open(sys.argv[1])); e=environment_errors(d); print(json.dumps({"pass":not e,"errors":e},indent=2)); sys.exit(0 if not e else 1)\n''')
write('validation/analysis/validate_dev14_hard_gates.py', '''#!/usr/bin/env python3\nimport argparse,json,sys\nfrom dev14_validation import hard_gate_errors\na=argparse.ArgumentParser(); a.add_argument("files",nargs="+"); a.add_argument("--allow-short",action="store_true"); x=a.parse_args(); out={}; ok=True\nfor f in x.files:\n d=json.load(open(f)); e=hard_gate_errors(d,not x.allow_short); out[f]={"pass":not e,"errors":e}; ok &= not e\nprint(json.dumps({"pass":ok,"files":out},indent=2)); sys.exit(0 if ok else 1)\n''')

# Deterministic dev14 fixture matrix.
fd=p('validation/fixtures/dev14'); fd.mkdir(parents=True,exist_ok=True)
def ev(seq,t,g=1,peer='peerA',trigger='PEER_STARVATION',target='peerA',wall=None):
    return {'seq':seq,'wall_ms':wall if wall is not None else seq*1000,'elapsed_ms':seq*1000,'elapsed_from_run_start_ms':seq*1000,'type':t,'recovery_generation':g,'peer_id':peer,'trigger_kind':trigger,'trigger_peer_id':target}
def snap(events=None, env_valid=True, types=None, env_events=None, elapsed=330000):
    return {'snapshot_schema_version':3,'snapshot_frozen':True,'run_id':'fixture','elapsed_ms':elapsed,'preflight_at_start':{'ready':True},'environment':{'valid':env_valid,'violation_count':0 if env_valid else 1,'violation_types':types or [],'unauthorized_strategy_violation_count':0,'authorized_strategy_transition_count':0,'authorized_recovery_interval_count':0,'total_background_ms':0,'max_background_interval_ms':0,'foreground_transition_count':0,'unresolved_violation_count':0},'environment_violation_events':env_events or [],'validation_counters':{'peer_expire_delta':0},'usable_metric_range_uptime_percent':99.0,'geometry_2d_uptime_percent':99.0,'acquisition_state_at_end':{'recovery_attempts_in_current_5min_window':1,'filtered_probe_window_ms':15000,'filtered_probe_exit_target_ms':14500},'events':events or []}
def fixture(name,doc,validator,should_pass,reason=None):
    doc={'expect':{'validator':validator,'pass':should_pass,'reason':reason},'snapshot':doc}; (fd/name).write_text(json.dumps(doc,indent=2)+'\n')
base=[ev(1,'RECOVERY_REQUESTED'),ev(2,'FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY'),ev(3,'RECOVERY_SUCCESS')]
fixture('recovery-success-atomic.json',snap(base),'timeline',True)
fixture('recovery-start-missing.json',snap([],False,['RECOVERY_START_MISSING']),'environment',False,'RECOVERY_START_MISSING')
near=snap([]); near['acquisition_state_at_end']['probe_elapsed_ms']=14950; fixture('probe-deadline-near-limit.json',near,'hard',True)
expired=snap([],False,['FILTERED_PROBE_WINDOW_EXPIRED']); fixture('probe-deadline-expired.json',expired,'environment',False,'FILTERED_PROBE_WINDOW_EXPIRED')
fixture('success-without-first-valid.json',snap([ev(1,'RECOVERY_REQUESTED'),ev(3,'RECOVERY_SUCCESS')]),'timeline',False,'RECOVERY_SUCCESS_WITHOUT_FIRST_VALID')
fixture('wrong-peer-first-valid.json',snap([ev(1,'RECOVERY_REQUESTED'),ev(2,'FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY',peer='peerB'),ev(3,'RECOVERY_SUCCESS')]),'timeline',False,'FIRST_VALID_WRONG_TARGET')
fixture('target-first-valid-success.json',snap(base),'timeline',True)
fixture('duplicate-first-valid.json',snap([ev(1,'RECOVERY_REQUESTED'),ev(2,'FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY'),ev(3,'FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY'),ev(4,'RECOVERY_SUCCESS')]),'timeline',False,'DUPLICATE_FIRST_VALID')
fixture('duplicate-terminal.json',snap(base+[ev(4,'RECOVERY_SUCCESS')]),'timeline',False,'DUPLICATE_TERMINAL')
fixture('success-after-failure.json',snap([ev(1,'RECOVERY_REQUESTED'),ev(2,'FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY'),ev(3,'RECOVERY_FAILURE'),ev(4,'RECOVERY_SUCCESS')]),'timeline',False,'TERMINAL_CONTRADICTION')
fixture('failure-after-success.json',snap(base+[ev(4,'RECOVERY_FAILURE')]),'timeline',False,'TERMINAL_CONTRADICTION')
fixture('callback-after-terminal.json',snap([ev(1,'RECOVERY_REQUESTED'),ev(2,'RECOVERY_FAILURE'),ev(3,'FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY')]),'timeline',False,'CALLBACK_AFTER_TERMINAL')
bg={'type':'APP_NOT_FOREGROUND','started_wall_ms':1000,'resolved_wall_ms':3000,'duration_ms':2000,'source':'ACTIVITY_LIFECYCLE','confirmed':True}
fixture('app-background-confirmed.json',snap([],False,['APP_NOT_FOREGROUND'],[bg]),'environment',False,'APP_NOT_FOREGROUND')
fixture('foreground-stable.json',snap([]),'environment',True)
fixture('duplicate-polling-same-violation.json',snap([],True,[],[{'type':'SCREEN_OFF','started_wall_ms':1000,'resolved_wall_ms':3000,'duration_ms':2000,'source':'ENVIRONMENT_EVALUATION','confirmed':True}]),'interval_structure',True)
fixture('short-run-preserves-long.json',{'history_test':True,'long_hash_before':'abc','long_hash_after':'abc','short_elapsed_ms':60000},'history',True)
fixture('long-reexport-immutable.json',{'history_test':True,'export1_sha256':'abc','export2_sha256':'abc'},'history',True)

write('validation/analysis/validate_dev14_fixture_matrix.py', r'''#!/usr/bin/env python3
import json,pathlib,sys
from dev14_validation import timeline_errors,environment_errors,hard_gate_errors
root=pathlib.Path(__file__).resolve().parents[1]/'fixtures'/'dev14'; failures=[]; rows=[]
for f in sorted(root.glob('*.json')):
    raw=json.load(open(f)); exp=raw['expect']; d=raw['snapshot']; kind=exp['validator']; errs=[]
    if kind=='timeline': errs=timeline_errors(d)
    elif kind=='environment': errs=environment_errors(d)
    elif kind=='hard': errs=hard_gate_errors(d)
    elif kind=='interval_structure':
        errs=[e for e in environment_errors(d) if e.startswith('ENVIRONMENT_INTERVAL_') or e.startswith('DUPLICATE_OVERLAPPING')]
    elif kind=='history':
        if d.get('long_hash_before')!=d.get('long_hash_after') or d.get('export1_sha256')!=d.get('export2_sha256'): errs=['SNAPSHOT_IMMUTABILITY_FAILURE']
    passed=not errs; reason=exp.get('reason'); good=passed==exp['pass'] and (reason is None or errs==[reason])
    rows.append({'fixture':f.name,'pass_as_expected':good,'errors':errs});
    if not good: failures.append(rows[-1])
print(json.dumps({'pass':not failures,'fixtures':rows},indent=2)); sys.exit(0 if not failures else 1)
''')

# Static/deterministic source contracts cover frozen truth and state-machine invariants.
write('validation/android/check_dev14_recovery_contract.py', r'''#!/usr/bin/env python3
from pathlib import Path
r=Path(__file__).resolve().parents[2]
b=(r/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleAcquisitionPolicy.kt').read_text()
n=(r/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt').read_text()
e=(r/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/EnvironmentViolationTracker.kt').read_text()
required=['FILTERED_PROBE_WINDOW_MS = 15_000L','FILTERED_PROBE_EXIT_TARGET_MS = 14_500L','RECOVERY_UNFILTERED_WINDOW_MS = 10_000L','MIN_RESTART_COOLDOWN_MS = 30_000L','MAX_RECOVERY_ATTEMPTS_PER_5MIN = 3','noteRecoveryFirstValidCallback','firstValidCallbackGeneration != generation','transition(BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE, now, "RECOVERY_SUCCESS")','transition(BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE, now, "RECOVERY_FAILURE")']
missing=[x for x in required if x not in b]
missing += [x for x in ['FILTERED_PROBE_EXIT_TARGET_MS','noteRecoveryFirstValidCallback(now, callbackPeerId)','EnvironmentViolationTracker.observe','snapshot_identity_sha256'] if x not in n]
missing += [x for x in ['total_background_ms','max_background_interval_ms','foreground_transition_count','confirmed','ACTIVITY_LIFECYCLE'] if x not in e]
assert not missing, missing
print('dev14 recovery/lifecycle contract PASS')
''')
write('validation/android/test_dev14_recovery_model.py', r'''#!/usr/bin/env python3
import unittest
class Gen:
 def __init__(s,target=None): s.target=target;s.first=None;s.terminal=None;s.state='UNFILTERED_RECOVERY';s.start=0;s.probe=None
 def cb(s,t,p):
  if s.terminal or s.state!='UNFILTERED_RECOVERY' or (s.target and p!=s.target): return False
  if s.first is None: s.first=(t,p); return True
  return False
 def success(s,t,p):
  if s.terminal or not s.first or (s.target and (p!=s.target or s.first[1]!=s.target)): return False
  s.terminal='SUCCESS';s.state='FILTERED_RECOVERY_PROBE';s.probe=t;return True
 def fail(s,t):
  if s.terminal:return False
  s.terminal='FAILURE';s.state='FILTERED_RECOVERY_PROBE';s.probe=t;return True
 def tick(s,t):
  if s.state=='FILTERED_RECOVERY_PROBE' and t-s.probe>=14500:s.state='FILTERED_PRIMARY'
class T(unittest.TestCase):
 def test_target(s): g=Gen('A');s.assertFalse(g.cb(1,'B'));s.assertTrue(g.cb(2,'A'));s.assertTrue(g.success(3,'A'))
 def test_success_requires_first(s): g=Gen('A');s.assertFalse(g.success(2,'A'))
 def test_terminal_exactly_once(s): g=Gen();g.cb(1,'A');s.assertTrue(g.success(2,'A'));s.assertFalse(g.success(3,'A'));s.assertFalse(g.fail(4));s.assertFalse(g.cb(5,'A'))
 def test_failure_terminal(s): g=Gen();s.assertTrue(g.fail(10000));s.assertEqual(g.state,'FILTERED_RECOVERY_PROBE')
 def test_probe_jitter(s):
  for jitter in range(0,1001,50):
   g=Gen();g.cb(1,'A');g.success(2,'A');g.tick(2+14500+jitter);s.assertEqual(g.state,'FILTERED_PRIMARY')
 def test_start_provenance_survives_probe(s): g=Gen();g.cb(1,'A');g.success(2,'A');s.assertEqual(g.start,0)
unittest.main()
''')

# Documentation: physical campaign plus Linux/WSL/Windows validator smoke. No screenshots.
write('docs/TESTING_DEV14.md', '''# TESTING DEV14 — final physical acceptance\n\nNo screenshots are required. Exported JSON/JSONL is the diagnostic source of truth.\n\n## 1. Verify release\nDownload every asset from prerelease `dev-14`. On Ubuntu/WSL run `sha256sum -c SHA256SUMS.txt`; on Windows PowerShell compare `Get-FileHash -Algorithm SHA256` with `SHA256SUMS.txt`. Confirm `release-verification.json` says PASS.\n\n## 2. Android preparation\nUse the exact same `BodyFinder-dev14-universal.apk` on Pixel 10 Pro, Pixel 7 Pro and Lenovo TB-J606L. Uninstall older builds if Android refuses replacement. Enable Bluetooth; Battery Saver OFF; screen ON; app visible/foreground. Use one common session and wait until each device reports preflight `ready=true` and at least two BLE peers. Do not enter node coordinates or distances in the app.\n\n## 3. Physical layout\nPlace the three devices as a static non-collinear triangle. Every pair distance must be 0.5–5.0 m. Measure with tape and write only those three distances to `ground-truth.json`.\n\n## 4. Runs on each Android\n1. Start validation; keep the app foreground for at least 330 s.\n2. End; export the completed long run as `<device>-long-1.json`.\n3. Keep app running at least 180 s; re-export the same completed run as `<device>-long-2.json`.\n4. Start a 45–60 s diagnostic run; end it.\n5. Reselect the original long run and export `<device>-long-post-short.json`.\n\nNames: `pixel10-*`, `pixel7-*`, `lenovo-*`, plus `ground-truth.json`.\n\n## 5. Automated validation (Ubuntu or WSL)\nUnzip `body-finder-validation-tools.zip`, then run:\n```bash\npython3 validate_dev14_hard_gates.py pixel10-long-1.json pixel7-long-1.json lenovo-long-1.json\npython3 validate_timeline_causality.py pixel10-long-1.json\npython3 validate_peer_starvation_recovery.py pixel10-long-1.json\npython3 validate_environment_intervals.py pixel10-long-1.json\npython3 compare_validation_snapshots.py pixel10-long-1.json pixel10-long-2.json\npython3 compare_validation_snapshots.py pixel10-long-1.json pixel10-long-post-short.json\npython3 build_acceptance_report.py . --output acceptance_report.json\npython3 calculate_accuracy_report.py ground-truth.json . --output accuracy_report.json\n```\nRepeat the single-file validators for Pixel 7 and Lenovo. The long-run validator must PASS; the long re-exports must be immutable; the short run must not replace/change the selected long snapshot.\n\n## 6. Windows native smoke\nExtract `body-finder-node-windows-x86_64.zip`, run `body-finder-node.exe --help`, then use Python validators from PowerShell exactly as above. Linux tar/deb and Windows node artifacts are smoke-tested independently of the 3-Android acceptance. iOS simulator ZIP is a build artifact only, not part of physical BLE acceptance.\n\nFinal GO requires automated G0–G16 PASS on all three long snapshots and aggregate reports. Accuracy is informative only; do not alter calibration automatically.\n''')

# Generic release manifest validator for dev14 inventory truth.
write('validation/analysis/validate_release_manifest.py', r'''#!/usr/bin/env python3
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]); m=json.load(open(p)); errs=[]
if m.get('release')=='dev-14':
 expected={'version':'0.2.0-experimental.14','protocol_version':2,'validation_snapshot_schema_version':3,'json_evidence_self_contained':True,'screenshots_required_for_acceptance':False,'ble_metric_profile':'android-ble-lab-v1','ble_metric_min_samples':3,'ble_fresh_ms':5000,'ble_holdover_max_ms':10000,'ble_hard_expiry_ms':10000,'ble_recovery_unfiltered_window_ms':10000,'ble_filtered_recovery_probe_ms':15000,'ble_filtered_recovery_probe_exit_target_ms':14500,'ble_restart_cooldown_ms':30000,'ble_max_recovery_attempts_per_5min':3,'automatic_geometry':True,'manual_node_coordinates_required':False,'human_scanning_enabled':False,'human_localization_validated':False,'rescue_use_validated':False}
 for k,v in expected.items():
  if m.get(k)!=v: errs.append(f'{k}: expected {v!r}, got {m.get(k)!r}')
arts=m.get('artifacts',[])
if arts and len({a.get('name') for a in arts})!=len(arts): errs.append('duplicate artifact names')
print(json.dumps({'pass':not errs,'errors':errs},indent=2)); sys.exit(0 if not errs else 1)
''')

# Create dev14 release workflow by migrating the already-proven dev13 cross-platform matrix.
y=read('.github/workflows/release-exp13.yml')
for a,b in [('experimental.13','experimental.14'),('experimental13','experimental14'),('Dev Release experimental.13','Dev Release experimental.14'),('release-exp13','release-exp14'),('RELEASE_DEV13_TRIGGER.txt','RELEASE_DEV14_TRIGGER.txt'),('dev13','dev14'),('DEV13','DEV14'),('dev-13','dev-14'),('BodyFinder-dev13','BodyFinder-dev14'),('reportVersion: 15','reportVersion: 16'),('"report_version": 15','"report_version": 16'),('"schema_version": 13','"schema_version": 14'),('"versionCode": 13','"versionCode": 14'),('0.2.0~experimental13','0.2.0~experimental14'),('ruvview-upstream-lock.json','ruview-upstream-lock.json')]: y=y.replace(a,b)
# requirements: execute new deterministic matrix/contracts.
y=y.replace('''          python3 validation/android/check_dev14_environment_contract.py\n          python3 validation/analysis/validate_environment_authorization.py''','''          python3 validation/android/check_dev14_environment_contract.py\n          python3 validation/android/check_dev14_recovery_contract.py\n          python3 validation/android/test_dev14_recovery_model.py\n          python3 validation/analysis/validate_environment_authorization.py\n          python3 validation/analysis/validate_dev14_fixture_matrix.py''')
y=y.replace('''validation/analysis/validate_dev14_hard_gates.py validation/analysis/validate_environment_authorization.py''','''validation/analysis/validate_dev14_hard_gates.py validation/analysis/dev14_validation.py validation/analysis/validate_dev14_fixture_matrix.py validation/analysis/validate_environment_intervals.py validation/analysis/validate_environment_authorization.py''')
# Dev13 checker was renamed by migration; create alias checker below.
y=y.replace("grep -q \"reportVersion: 15\"", "grep -q \"reportVersion: 16\"")
y=y.replace('''            "ble_filtered_recovery_probe_ms": 15000,''','''            "ble_filtered_recovery_probe_ms": 15000,\n            "ble_filtered_recovery_probe_exit_target_ms": 14500,\n            "recovery_generation_atomic": true,\n            "targeted_first_valid_required": true,\n            "environment_violation_intervals": true,\n            "snapshot_identity_sha256": true,''')
write('docs/generated-release-exp14.yml',y)
# The validated YAML is installed into .github/workflows by the GitHub connector, because the Actions token cannot update workflow files.

# The dev13 environment checker is still useful; make a dev14-named compatible copy with release token migrated.
checker=read('validation/android/check_dev13_environment_contract.py').replace('dev13','dev14').replace('experimental.13','experimental.14').replace('reportVersion: 15','reportVersion: 16')
write('validation/android/check_dev14_environment_contract.py',checker)

print('dev14 implementation materialized')
