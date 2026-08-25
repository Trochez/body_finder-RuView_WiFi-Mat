from pathlib import Path
import json, re, textwrap

ROOT = Path(__file__).resolve().parents[1]

def p(rel): return ROOT / rel

def read(rel): return p(rel).read_text()

def write(rel, content):
    path = p(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)

def replace_once(rel, old, new):
    s = read(rel)
    if old not in s:
        raise SystemExit(f'anchor missing in {rel}: {old[:100]!r}')
    s2 = s.replace(old, new, 1)
    write(rel, s2)

# ---- Version truth ---------------------------------------------------------
write('apps/mobile/src/version.ts', '''export const RELEASE = Object.freeze({
  build: '0.2.0-experimental.13',
  reportVersion: 15,
  versionCode: 13,
  releaseIteration: 'experimental.13',
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
app['expo']['android']['versionCode'] = 13
app['expo']['extra']['releaseIteration'] = 'experimental.13'
write('apps/mobile/app.json', json.dumps(app, indent=2, ensure_ascii=False) + '\n')

app_tsx = read('apps/mobile/App.tsx')
for old, new in [
    ('experimental.12', 'experimental.13'),
    ('dev12-self-contained-json-evidence-v1', 'dev13-self-contained-json-evidence-v2'),
    ('dev-12', 'dev-13'),
    ('experimental.12 self-contained validation result', 'experimental.13 self-contained validation result'),
]:
    app_tsx = app_tsx.replace(old, new)
write('apps/mobile/App.tsx', app_tsx)

# ---- Pure recovery-aware strategy evaluator --------------------------------
write('apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/EnvironmentStrategyValidator.kt', r'''package com.trochez.bodyfindernative

internal data class RecoveryAuthorizationContext(
  val strategy: BleAcquisitionStrategy,
  val activeRecoveryGeneration: Long?,
  val strategyRecoveryGeneration: Long?,
  val triggerKind: RecoveryTriggerKind?,
  val triggerPeerId: String?,
  val recoveryStartedWallMs: Long?,
  val strategySinceWallMs: Long,
  val nowWallMs: Long,
  val filterMode: String,
  val hardwareFilterCount: Int,
)

internal data class StrategyEnvironmentDecision(
  val valid: Boolean,
  val authorized: Boolean,
  val violationType: String?,
  val authorizationReason: String,
)

internal object EnvironmentStrategyValidator {
  private val allowedTriggers = setOf(RecoveryTriggerKind.FULL_COHORT_STALL, RecoveryTriggerKind.PEER_STARVATION)

  fun evaluate(c: RecoveryAuthorizationContext): StrategyEnvironmentDecision {
    return when (c.strategy) {
      BleAcquisitionStrategy.FILTERED_PRIMARY -> {
        if (c.filterMode == "MANUFACTURER_FILTERED" && c.hardwareFilterCount > 0) {
          StrategyEnvironmentDecision(true, true, null, "FILTERED_PRIMARY_WITH_HARDWARE_FILTER")
        } else {
          StrategyEnvironmentDecision(false, false, "PRIMARY_FILTER_CONFIGURATION_INVALID", "PRIMARY_REQUIRES_MANUFACTURER_FILTER")
        }
      }
      BleAcquisitionStrategy.UNFILTERED_RECOVERY -> {
        val gen = c.activeRecoveryGeneration
        val sg = c.strategyRecoveryGeneration
        when {
          gen == null || sg == null -> StrategyEnvironmentDecision(false, false, "UNFILTERED_RECOVERY_WITHOUT_GENERATION", "RECOVERY_GENERATION_REQUIRED")
          gen != sg -> StrategyEnvironmentDecision(false, false, "RECOVERY_GENERATION_MISMATCH", "STRATEGY_GENERATION_MUST_MATCH_ACTIVE_GENERATION")
          c.triggerKind !in allowedTriggers -> StrategyEnvironmentDecision(false, false, "RECOVERY_TRIGGER_INVALID", "KNOWN_RECOVERY_TRIGGER_REQUIRED")
          c.recoveryStartedWallMs == null -> StrategyEnvironmentDecision(false, false, "RECOVERY_START_MISSING", "RECOVERY_START_REQUIRED")
          c.nowWallMs - c.recoveryStartedWallMs > BleAcquisitionPolicy.RECOVERY_UNFILTERED_WINDOW_MS -> StrategyEnvironmentDecision(false, false, "RECOVERY_WINDOW_EXPIRED", "UNFILTERED_WINDOW_IS_BOUNDED")
          c.filterMode != "UNFILTERED" || c.hardwareFilterCount != 0 -> StrategyEnvironmentDecision(false, false, "RECOVERY_FILTER_CONFIGURATION_INVALID", "UNFILTERED_RECOVERY_REQUIRES_ZERO_HARDWARE_FILTERS")
          else -> StrategyEnvironmentDecision(true, true, null, "AUTHORIZED_BOUNDED_RECOVERY_GENERATION")
        }
      }
      BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE -> {
        val gen = c.activeRecoveryGeneration
        val sg = c.strategyRecoveryGeneration
        when {
          gen == null || sg == null -> StrategyEnvironmentDecision(false, false, "FILTERED_PROBE_WITHOUT_PROVENANCE", "RECOVERY_PROVENANCE_REQUIRED")
          gen != sg -> StrategyEnvironmentDecision(false, false, "RECOVERY_GENERATION_MISMATCH", "PROBE_GENERATION_MUST_MATCH_ACTIVE_GENERATION")
          c.triggerKind !in allowedTriggers -> StrategyEnvironmentDecision(false, false, "RECOVERY_TRIGGER_INVALID", "KNOWN_RECOVERY_TRIGGER_REQUIRED")
          c.nowWallMs - c.strategySinceWallMs > BleAcquisitionPolicy.FILTERED_PROBE_WINDOW_MS -> StrategyEnvironmentDecision(false, false, "FILTERED_PROBE_WINDOW_EXPIRED", "FILTERED_PROBE_WINDOW_IS_BOUNDED")
          c.filterMode != "MANUFACTURER_FILTERED" || c.hardwareFilterCount <= 0 -> StrategyEnvironmentDecision(false, false, "PROBE_FILTER_CONFIGURATION_INVALID", "FILTERED_PROBE_REQUIRES_MANUFACTURER_FILTER")
          else -> StrategyEnvironmentDecision(true, true, null, "AUTHORIZED_FILTERED_RECOVERY_PROBE")
        }
      }
      else -> StrategyEnvironmentDecision(false, false, "UNAUTHORIZED_ACQUISITION_STRATEGY", "RECOVERY_ARBITER_PROVENANCE_REQUIRED")
    }
  }
}
''')

# ---- Recovery provenance ----------------------------------------------------
ble_rel = 'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleAcquisitionPolicy.kt'
ble = read(ble_rel).replace('experimental.11', 'experimental.13').replace('experimental.12', 'experimental.13')
ble = ble.replace(
'''  @Volatile private var activeRecoveryGeneration: Long? = null\n  @Volatile private var activeRecoveryTriggerKind: RecoveryTriggerKind? = null''',
'''  @Volatile private var activeRecoveryGeneration: Long? = null\n  @Volatile private var strategyRecoveryGeneration: Long? = null\n  @Volatile private var activeRecoveryTriggerKind: RecoveryTriggerKind? = null''')
ble = ble.replace(
'''    activeRecoveryGeneration = null\n    activeRecoveryTriggerKind = null''',
'''    activeRecoveryGeneration = null\n    strategyRecoveryGeneration = null\n    activeRecoveryTriggerKind = null''', 1)
ble = ble.replace(
'''  fun activeRecoveryGeneration(): Long? = activeRecoveryGeneration\n  fun activeRecoveryTriggerKind(): RecoveryTriggerKind? = activeRecoveryTriggerKind''',
'''  fun activeRecoveryGeneration(): Long? = activeRecoveryGeneration\n  fun strategyRecoveryGeneration(): Long? = strategyRecoveryGeneration\n  fun activeRecoveryTriggerKind(): RecoveryTriggerKind? = activeRecoveryTriggerKind''')
old_transition = '''  @Synchronized\n  fun transition(next: BleAcquisitionStrategy, now: Long, reason: String) {\n    if (strategy == next) return\n    accumulateCurrentMode(now)\n    strategy = next\n    strategySinceWallMs = now\n    lastStrategyReason = reason\n    transitionCount++\n    ValidationEventLog.record("ACQUISITION_STRATEGY_CHANGED", "$reason:${next.name}", now = now)\n    if (next == BleAcquisitionStrategy.FILTERED_PRIMARY || next == BleAcquisitionStrategy.FAILED_SAFE) {\n      activeRecoveryGeneration = null\n      activeRecoveryTriggerKind = null\n      activeRecoveryTriggerPeerId = null\n    }\n  }'''
new_transition = '''  @Synchronized\n  fun transition(next: BleAcquisitionStrategy, now: Long, reason: String) {\n    if (strategy == next) return\n    val previous = strategy\n    accumulateCurrentMode(now)\n    strategy = next\n    strategySinceWallMs = now\n    lastStrategyReason = reason\n    strategyRecoveryGeneration = if (next == BleAcquisitionStrategy.UNFILTERED_RECOVERY || next == BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE) activeRecoveryGeneration else null\n    transitionCount++\n    ValidationEventLog.record(\n      "ACQUISITION_STRATEGY_CHANGED", "$reason:${next.name}", now = now,\n      fromStrategy = previous.name, toStrategy = next.name,\n    )\n    if (next == BleAcquisitionStrategy.FILTERED_PRIMARY || next == BleAcquisitionStrategy.FAILED_SAFE) {\n      activeRecoveryGeneration = null\n      strategyRecoveryGeneration = null\n      activeRecoveryTriggerKind = null\n      activeRecoveryTriggerPeerId = null\n      recoveryStartedWallMs = null\n    }\n  }'''
if old_transition not in ble: raise SystemExit('transition anchor missing')
ble = ble.replace(old_transition, new_transition)
old_begin = '''  ) {\n    if (activeRecoveryGeneration != null) return\n    recoveryAttemptCountTotal++'''
new_begin = '''  ) {\n    val active = activeRecoveryGeneration\n    if (active != null && recoveryTerminalGeneration.get() != active) return\n    if (active != null) {\n      activeRecoveryGeneration = null\n      strategyRecoveryGeneration = null\n      activeRecoveryTriggerKind = null\n      activeRecoveryTriggerPeerId = null\n      recoveryStartedWallMs = null\n    }\n    recoveryAttemptCountTotal++'''
if old_begin not in ble: raise SystemExit('beginRecovery anchor missing')
ble = ble.replace(old_begin, new_begin, 1)
ble = ble.replace(
'''    .put("active_recovery_trigger_kind", activeRecoveryTriggerKind?.name ?: JSONObject.NULL)''',
'''    .put("active_recovery_generation", activeRecoveryGeneration ?: JSONObject.NULL)\n    .put("strategy_recovery_generation", strategyRecoveryGeneration ?: JSONObject.NULL)\n    .put("active_recovery_trigger_kind", activeRecoveryTriggerKind?.name ?: JSONObject.NULL)''')
write(ble_rel, ble)

# ---- Timeline transition provenance ----------------------------------------
event_rel = 'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/ValidationEventLog.kt'
e = read(event_rel)
e = e.replace(
'''  val peerId: String?,\n  val triggerKind: String?,\n)''',
'''  val peerId: String?,\n  val triggerKind: String?,\n  val fromStrategy: String?,\n  val toStrategy: String?,\n  val authorizationReason: String?,\n)''')
e = e.replace(
'''    peerId: String? = null,\n    triggerKind: String? = null,\n  ) {''',
'''    peerId: String? = null,\n    triggerKind: String? = null,\n    fromStrategy: String? = null,\n    toStrategy: String? = null,\n    authorizationReason: String? = null,\n  ) {''')
e = e.replace(
'''        rs, y, generation, peerId,\n        triggerKind ?: BleAcquisitionPolicy.activeRecoveryTriggerKind()?.name,\n      )''',
'''        rs, y, generation, peerId,\n        triggerKind ?: BleAcquisitionPolicy.activeRecoveryTriggerKind()?.name,\n        fromStrategy, toStrategy, authorizationReason,\n      )''')
e = e.replace(
'''          .put("trigger_peer_id", if (e.triggerKind == RecoveryTriggerKind.PEER_STARVATION.name) (e.peerId ?: JSONObject.NULL) else JSONObject.NULL)''',
'''          .put("trigger_peer_id", if (e.triggerKind == RecoveryTriggerKind.PEER_STARVATION.name) (e.peerId ?: JSONObject.NULL) else JSONObject.NULL)\n          .put("from_strategy", e.fromStrategy ?: JSONObject.NULL)\n          .put("to_strategy", e.toStrategy ?: JSONObject.NULL)\n          .put("authorization_reason", e.authorizationReason ?: JSONObject.NULL)''')
write(event_rel, e)

# ---- Validation state / frozen preflight / environment counters ------------
native_rel = 'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt'
n = read(native_rel)
# new runtime fields
n = n.replace(
'''  @Volatile private var environmentViolationTypes: String = ""\n  @Volatile private var baselineStrategyTransitions: Long = 0''',
'''  @Volatile private var environmentViolationTypes: String = ""\n  @Volatile private var preflightAtStartJson: String = "{}"\n  @Volatile private var authorizedStrategyTransitionCount: Long = 0\n  @Volatile private var authorizedRecoveryIntervalCount: Long = 0\n  @Volatile private var unauthorizedStrategyViolationCount: Long = 0\n  @Volatile private var lastEnvironmentStrategy: String? = null\n  @Volatile private var lastAuthorizedRecoveryGeneration: Long? = null\n  @Volatile private var baselineStrategyTransitions: Long = 0''')
# start signature
n = n.replace(
'''  fun start(now: Long, peerExpire: Long, rebind: Long, scanRestart: Long, tx: Long, rx: Long): String {''',
'''  fun start(now: Long, peerExpire: Long, rebind: Long, scanRestart: Long, tx: Long, rx: Long, preflightJson: String): String {''')
n = n.replace(
'''    environmentViolationTypes = ""\n    baselineStrategyTransitions = BleAcquisitionPolicy.transitionCount()''',
'''    environmentViolationTypes = ""\n    preflightAtStartJson = try { JSONObject(preflightJson).toString() } catch (_: Throwable) { "{}" }\n    authorizedStrategyTransitionCount = 0\n    authorizedRecoveryIntervalCount = 0\n    unauthorizedStrategyViolationCount = 0\n    lastEnvironmentStrategy = BleAcquisitionStrategy.FILTERED_PRIMARY.name\n    lastAuthorizedRecoveryGeneration = null\n    baselineStrategyTransitions = BleAcquisitionPolicy.transitionCount()''')
# environment frozen
n = n.replace(
'''    val environment = JSONObject()\n      .put("valid", environmentViolationCount == 0L)\n      .put("violation_count", environmentViolationCount)\n      .put("first_violation_wall_ms", firstEnvironmentViolationWallMs ?: JSONObject.NULL)\n      .put("violation_types", if (environmentViolationTypes.isBlank()) JSONArray() else JSONArray(environmentViolationTypes.split(',')))''',
'''    val environment = JSONObject()\n      .put("valid", environmentViolationCount == 0L)\n      .put("violation_count", environmentViolationCount)\n      .put("first_violation_wall_ms", firstEnvironmentViolationWallMs ?: JSONObject.NULL)\n      .put("violation_types", if (environmentViolationTypes.isBlank()) JSONArray() else JSONArray(environmentViolationTypes.split(',')))\n      .put("authorized_strategy_transition_count", authorizedStrategyTransitionCount)\n      .put("authorized_recovery_interval_count", authorizedRecoveryIntervalCount)\n      .put("unauthorized_strategy_violation_count", unauthorizedStrategyViolationCount)''')
n = n.replace('.put("snapshot_schema_version", 2)', '.put("snapshot_schema_version", 3)')
n = n.replace(
'''      .put("environment", environment)\n      .put("validation_counters", counters)''',
'''      .put("preflight_at_start", try { JSONObject(preflightAtStartJson) } catch (_: Throwable) { JSONObject() })\n      .put("environment", environment)\n      .put("validation_counters", counters)''')
# replace recorder method
old_rec = '''  @Synchronized\n  fun recordEnvironmentViolation(now: Long, issues: List<String>) {\n    if (runId == null || endedWallMs != null || issues.isEmpty()) return\n    environmentViolationCount++\n    if (firstEnvironmentViolationWallMs == null) firstEnvironmentViolationWallMs = now\n    environmentViolationTypes = (environmentViolationTypes.split(',').filter { it.isNotBlank() } + issues).distinct().joinToString(",")\n  }'''
new_rec = '''  @Synchronized\n  fun recordEnvironmentEvaluation(\n    now: Long,\n    issues: List<String>,\n    decision: StrategyEnvironmentDecision,\n    strategy: BleAcquisitionStrategy,\n    recoveryGeneration: Long?,\n    triggerKind: RecoveryTriggerKind?,\n    triggerPeerId: String?,\n  ) {\n    if (runId == null || endedWallMs != null) return\n    val previous = lastEnvironmentStrategy\n    if (previous != strategy.name && decision.authorized) {\n      authorizedStrategyTransitionCount++\n      ValidationEventLog.record(\n        "ENVIRONMENT_STRATEGY_TRANSITION_AUTHORIZED", decision.authorizationReason, now = now,\n        peerId = triggerPeerId, triggerKind = triggerKind?.name,\n        fromStrategy = previous, toStrategy = strategy.name, authorizationReason = decision.authorizationReason,\n      )\n    }\n    lastEnvironmentStrategy = strategy.name\n    if (decision.authorized && (strategy == BleAcquisitionStrategy.UNFILTERED_RECOVERY || strategy == BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE) && recoveryGeneration != null && lastAuthorizedRecoveryGeneration != recoveryGeneration) {\n      authorizedRecoveryIntervalCount++\n      lastAuthorizedRecoveryGeneration = recoveryGeneration\n    }\n    if (!decision.valid) unauthorizedStrategyViolationCount++\n    if (issues.isEmpty()) return\n    environmentViolationCount++\n    if (firstEnvironmentViolationWallMs == null) firstEnvironmentViolationWallMs = now\n    environmentViolationTypes = (environmentViolationTypes.split(',').filter { it.isNotBlank() } + issues).distinct().joinToString(",")\n  }'''
if old_rec not in n: raise SystemExit('environment recorder anchor missing')
n = n.replace(old_rec, new_rec)
# add live fields after environment types
n = n.replace(
'''      .put("environment_violation_types", if (environmentViolationTypes.isBlank()) JSONArray() else JSONArray(environmentViolationTypes.split(',')))\n      .put("strategy_transition_delta",''',
'''      .put("environment_violation_types", if (environmentViolationTypes.isBlank()) JSONArray() else JSONArray(environmentViolationTypes.split(',')))\n      .put("preflight_at_start", try { JSONObject(preflightAtStartJson) } catch (_: Throwable) { JSONObject() })\n      .put("authorized_strategy_transition_count", authorizedStrategyTransitionCount)\n      .put("authorized_recovery_interval_count", authorizedRecoveryIntervalCount)\n      .put("unauthorized_strategy_violation_count", unauthorizedStrategyViolationCount)\n      .put("strategy_transition_delta",''')
# summary contract
old_summary = '''      out.put(JSONObject()\n        .put("run_id", run.runId)\n        .put("started_wall_ms", j.opt("started_wall_ms"))\n        .put("ended_wall_ms", j.opt("ended_wall_ms"))\n        .put("elapsed_ms", j.optLong("elapsed_ms"))\n        .put("snapshot_frozen", j.optBoolean("snapshot_frozen"))\n        .put("snapshot_schema_version", j.optInt("snapshot_schema_version")))'''
new_summary = '''      out.put(JSONObject()\n        .put("run_id", run.runId)\n        .put("started_wall_ms", j.opt("started_wall_ms"))\n        .put("ended_wall_ms", j.opt("ended_wall_ms"))\n        .put("elapsed_ms", j.optLong("elapsed_ms"))\n        .put("snapshot_frozen", j.optBoolean("snapshot_frozen"))\n        .put("snapshot_schema_version", j.optInt("snapshot_schema_version"))\n        .put("acceptance_minimum_ms", j.optLong("acceptance_minimum_ms"))\n        .put("acceptance_duration_eligible", j.optBoolean("acceptance_duration_eligible"))\n        .put("short_diagnostic_run", j.optBoolean("short_diagnostic_run"))\n        .put("environment_valid", j.optBoolean("environment_valid"))\n        .put("usable_metric_range_uptime_percent", j.opt("usable_metric_range_uptime_percent"))\n        .put("geometry_2d_uptime_percent", j.opt("geometry_2d_uptime_percent"))\n        .put("peer_expire_delta", j.optLong("peer_expire_delta"))\n        .put("recovery_attempt_delta", j.optLong("recovery_attempt_delta")))'''
if old_summary not in n: raise SystemExit('summary anchor missing')
n = n.replace(old_summary, new_summary)
# replace physical/strategy/preflight functions
start = n.index('  private fun validationEnvironmentIssues(ctx: Context): List<String> {')
end = n.index('\n  private fun deviceReport(ctx: Context)', start)
new_env = r'''  private fun physicalValidationIssues(ctx: Context): List<String> {
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
    if (expectedKnownPeerCount() < 2) issues += "EXPECTED_BLE_PEERS_LT_2"
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
      .put("expected_ble_peers_ready", expectedKnownPeerCount() >= 2)
      .put("acquisition_strategy", strategy.name)
      .put("filter_mode", filterMode)
      .put("hardware_filter_count", hardwareFilterCount)
      .put("location_requirement_applicable", locationApplicable)
      .put("location_service_enabled", if (locationApplicable) (locationServiceEnabled(ctx) ?: JSONObject.NULL) else JSONObject.NULL)
      .put("blocking_reasons", JSONArray(blocking.distinct()))
      .put("issues", JSONArray(blocking.distinct()))
      .put("acceptance_minimum_ms", 300_000L)
      .put("recommended_long_run_ms", 330_000L)
  }
'''
n = n[:start] + new_env + n[end:]
# startValidationRun strict frozen preflight
old_start = '''    Function("startValidationRun") {\n      val ctx = appContext.reactContext ?: return@Function "VALIDATION_ENVIRONMENT_INVALID:NO_CONTEXT"\n      val issues = validationEnvironmentIssues(ctx)\n      if (issues.isNotEmpty()) return@Function "VALIDATION_ENVIRONMENT_INVALID:${issues.joinToString(",")}"\n      val now = System.currentTimeMillis()\n      FabricRuntime.snapshotAcquisitionForValidation()\n      val id = ValidationRuntime.start(\n        now,\n        FabricRuntime.peerExpireCount.get(),\n        FabricRuntime.totalRebinds(),\n        FabricRuntime.scanRestartCount.get(),\n        FabricRuntime.txPackets.get(),\n        FabricRuntime.rxPackets.get(),\n      )'''
new_start = '''    Function("startValidationRun") {\n      val ctx = appContext.reactContext ?: return@Function "VALIDATION_ENVIRONMENT_INVALID:NO_CONTEXT"\n      val now = System.currentTimeMillis()\n      val preflight = validationPreflight(ctx, now)\n      val blocking = preflight.optJSONArray("blocking_reasons") ?: JSONArray()\n      if (blocking.length() > 0) {\n        val reasons = (0 until blocking.length()).map { blocking.optString(it) }\n        return@Function "VALIDATION_ENVIRONMENT_INVALID:${reasons.joinToString(",")}"\n      }\n      FabricRuntime.snapshotAcquisitionForValidation()\n      val id = ValidationRuntime.start(\n        now,\n        FabricRuntime.peerExpireCount.get(),\n        FabricRuntime.totalRebinds(),\n        FabricRuntime.scanRestartCount.get(),\n        FabricRuntime.txPackets.get(),\n        FabricRuntime.rxPackets.get(),\n        preflight.toString(),\n      )'''
if old_start not in n: raise SystemExit('start validation anchor missing')
n = n.replace(old_start, new_start)
# recovery physical gate only
n = n.replace(
'''          val environmentAllowsRecovery = ValidationRuntime.runId == null || ValidationRuntime.endedWallMs != null || validationEnvironmentIssues(ctx).isEmpty()''',
'''          val environmentAllowsRecovery = ValidationRuntime.runId == null || ValidationRuntime.endedWallMs != null || physicalValidationIssues(ctx).isEmpty()''')
# acquisition provenance body replacement
old_prov = '''  private fun acquisitionProvenance(now:Long)=JSONObject()\n    .put("logical_acquisition_strategy",BleAcquisitionPolicy.currentStrategy().name)\n    .put("strategy_since_wall_ms",BleAcquisitionPolicy.strategySinceMs())\n    .put("strategy_reason",BleAcquisitionPolicy.lastStrategyReason())\n    .put("android_scan_settings",JSONObject().put("scan_mode","LOW_LATENCY").put("callback_type","ALL_MATCHES").put("report_delay_ms",BleAcquisitionPolicy.REPORT_DELAY_MS).put("match_mode",BleAcquisitionPolicy.matchModeLabel()).put("num_matches",BleAcquisitionPolicy.numMatchesLabel()))\n    .put("filter_configuration",JSONObject().put("mode",if(BleAcquisitionPolicy.currentStrategy()==BleAcquisitionStrategy.UNFILTERED_RECOVERY) "UNFILTERED" else "MANUFACTURER_FILTERED").put("hardware_filter_count",if(BleAcquisitionPolicy.currentStrategy()==BleAcquisitionStrategy.UNFILTERED_RECOVERY)0 else 1).put("manufacturer_id",MANUFACTURER_ID).put("body_finder_prefix","4246"))\n    .put("scan_generation",FabricRuntime.scanGeneration.get()).put("scanner_started_wall_ms",FabricRuntime.bleScanStartedWallMs ?: JSONObject.NULL)'''
new_prov = '''  private fun acquisitionProvenance(now: Long): JSONObject {\n    val strategy = BleAcquisitionPolicy.currentStrategy()\n    val (filterMode, hardwareFilterCount) = strategyFilterMode(strategy)\n    val decision = strategyEnvironmentDecision(now)\n    return JSONObject()\n      .put("logical_acquisition_strategy", strategy.name)\n      .put("strategy_since_wall_ms", BleAcquisitionPolicy.strategySinceMs())\n      .put("strategy_reason", BleAcquisitionPolicy.lastStrategyReason())\n      .put("active_recovery_generation", BleAcquisitionPolicy.activeRecoveryGeneration() ?: JSONObject.NULL)\n      .put("strategy_recovery_generation", BleAcquisitionPolicy.strategyRecoveryGeneration() ?: JSONObject.NULL)\n      .put("active_recovery_trigger_kind", BleAcquisitionPolicy.activeRecoveryTriggerKind()?.name ?: JSONObject.NULL)\n      .put("active_recovery_trigger_peer_id", BleAcquisitionPolicy.activeRecoveryTriggerPeerId() ?: JSONObject.NULL)\n      .put("recovery_started_wall_ms", BleAcquisitionPolicy.recoveryStartedMs() ?: JSONObject.NULL)\n      .put("environment_authorization", JSONObject()\n        .put("valid", decision.valid)\n        .put("authorized", decision.authorized)\n        .put("violation_type", decision.violationType ?: JSONObject.NULL)\n        .put("authorization_reason", decision.authorizationReason))\n      .put("android_scan_settings", JSONObject().put("scan_mode","LOW_LATENCY").put("callback_type","ALL_MATCHES").put("report_delay_ms",BleAcquisitionPolicy.REPORT_DELAY_MS).put("match_mode",BleAcquisitionPolicy.matchModeLabel()).put("num_matches",BleAcquisitionPolicy.numMatchesLabel()))\n      .put("filter_configuration", JSONObject().put("mode", filterMode).put("hardware_filter_count", hardwareFilterCount).put("manufacturer_id",MANUFACTURER_ID).put("body_finder_prefix","4246"))\n      .put("scan_generation", FabricRuntime.scanGeneration.get())\n      .put("scanner_started_wall_ms", FabricRuntime.bleScanStartedWallMs ?: JSONObject.NULL)\n  }'''
if old_prov not in n: raise SystemExit('provenance anchor missing')
n = n.replace(old_prov, new_prov)
# validation recorder use pair
old_vrd = '''  private fun validationRunDiagnostics(ctx: Context, now: Long = System.currentTimeMillis()): JSONObject {\n    if (ValidationRuntime.runId != null && ValidationRuntime.endedWallMs == null) {\n      ValidationRuntime.recordEnvironmentViolation(now, validationEnvironmentIssues(ctx))\n    }'''
new_vrd = '''  private fun validationRunDiagnostics(ctx: Context, now: Long = System.currentTimeMillis()): JSONObject {\n    if (ValidationRuntime.runId != null && ValidationRuntime.endedWallMs == null) {\n      val (issues, decision) = validationEnvironmentIssues(ctx, now)\n      ValidationRuntime.recordEnvironmentEvaluation(\n        now, issues, decision, BleAcquisitionPolicy.currentStrategy(),\n        BleAcquisitionPolicy.activeRecoveryGeneration(), BleAcquisitionPolicy.activeRecoveryTriggerKind(), BleAcquisitionPolicy.activeRecoveryTriggerPeerId(),\n      )\n    }'''
if old_vrd not in n: raise SystemExit('validation diagnostics anchor missing')
n = n.replace(old_vrd, new_vrd)
old_loop = '''          if (ValidationRuntime.runId != null && ValidationRuntime.endedWallMs == null) {\n            ValidationRuntime.recordEnvironmentViolation(now, validationEnvironmentIssues(ctx))\n          }'''
new_loop = '''          if (ValidationRuntime.runId != null && ValidationRuntime.endedWallMs == null) {\n            val (issues, decision) = validationEnvironmentIssues(ctx, now)\n            ValidationRuntime.recordEnvironmentEvaluation(\n              now, issues, decision, BleAcquisitionPolicy.currentStrategy(),\n              BleAcquisitionPolicy.activeRecoveryGeneration(), BleAcquisitionPolicy.activeRecoveryTriggerKind(), BleAcquisitionPolicy.activeRecoveryTriggerPeerId(),\n            )\n          }'''
if old_loop not in n: raise SystemExit('network loop env anchor missing')
n = n.replace(old_loop, new_loop)
n = n.replace('dev12-self-contained-json-evidence-v1', 'dev13-self-contained-json-evidence-v2')
write(native_rel, n)

# ---- Schema v3 --------------------------------------------------------------
write('protocol/schemas/validation-run-snapshot-v3.json', '''{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "validation-run-snapshot-v3.schema.json",
  "title": "Body Finder CompletedValidationRun v3",
  "type": "object",
  "required": ["snapshot_schema_version","run_id","started_wall_ms","ended_wall_ms","elapsed_ms","snapshot_frozen","preflight_at_start","environment","validation_counters","acquisition_state_at_end","per_peer_at_end","system_ranging_at_end","events","geometry_at_end","fused_range_observations_at_end","graph_diagnostics_at_end"],
  "properties": {
    "snapshot_schema_version": {"const": 3},
    "run_id": {"type":"string","minLength":1},
    "started_wall_ms": {"type":"integer","minimum":0},
    "ended_wall_ms": {"type":"integer","minimum":0},
    "elapsed_ms": {"type":"integer","minimum":0},
    "snapshot_frozen": {"const":true},
    "preflight_at_start": {
      "type":"object",
      "required":["ready","wall_ms","bluetooth_on","ble_permissions_ready","battery_saver_off","screen_on","app_foreground","foreground_service_running","ble_scanner_running","expected_ble_peer_count","expected_ble_peers_ready","acquisition_strategy","filter_mode","hardware_filter_count","location_requirement_applicable","blocking_reasons"]
    },
    "environment": {
      "type":"object",
      "required":["valid","violation_count","violation_types","authorized_strategy_transition_count","authorized_recovery_interval_count","unauthorized_strategy_violation_count"]
    },
    "validation_counters":{"type":"object"},
    "acquisition_state_at_end":{"type":"object"},
    "per_peer_at_end":{"type":"array"},
    "system_ranging_at_end":{"type":"object"},
    "events":{"type":"array","items":{"type":"object","required":["seq","wall_ms","elapsed_ms","type"]}},
    "geometry_at_end":{},
    "locally_computed_geometry_at_end":{},
    "fused_range_observations_at_end":{"type":"array"},
    "graph_diagnostics_at_end":{},
    "reciprocal_fusion_at_end":{},
    "measurement_health_at_end":{}
  },
  "additionalProperties": true
}
''')

# ---- Deterministic environment fixtures ------------------------------------
fixtures = {
'healthy-primary.json': dict(strategy='FILTERED_PRIMARY', active_recovery_generation=None, strategy_recovery_generation=None, trigger_kind=None, recovery_started_wall_ms=None, strategy_since_wall_ms=1000, now_wall_ms=2000, filter_mode='MANUFACTURER_FILTERED', hardware_filter_count=1, expected_valid=True),
'authorized-peer-recovery.json': dict(strategy='UNFILTERED_RECOVERY', active_recovery_generation=7, strategy_recovery_generation=7, trigger_kind='PEER_STARVATION', recovery_started_wall_ms=1000, strategy_since_wall_ms=1000, now_wall_ms=5000, filter_mode='UNFILTERED', hardware_filter_count=0, expected_valid=True),
'authorized-cohort-recovery.json': dict(strategy='UNFILTERED_RECOVERY', active_recovery_generation=8, strategy_recovery_generation=8, trigger_kind='FULL_COHORT_STALL', recovery_started_wall_ms=1000, strategy_since_wall_ms=1000, now_wall_ms=9000, filter_mode='UNFILTERED', hardware_filter_count=0, expected_valid=True),
'authorized-filtered-probe.json': dict(strategy='FILTERED_RECOVERY_PROBE', active_recovery_generation=8, strategy_recovery_generation=8, trigger_kind='FULL_COHORT_STALL', recovery_started_wall_ms=None, strategy_since_wall_ms=1000, now_wall_ms=12000, filter_mode='MANUFACTURER_FILTERED', hardware_filter_count=1, expected_valid=True),
'unfiltered-without-generation.json': dict(strategy='UNFILTERED_RECOVERY', active_recovery_generation=None, strategy_recovery_generation=None, trigger_kind='PEER_STARVATION', recovery_started_wall_ms=1000, strategy_since_wall_ms=1000, now_wall_ms=2000, filter_mode='UNFILTERED', hardware_filter_count=0, expected_valid=False),
'stale-generation.json': dict(strategy='UNFILTERED_RECOVERY', active_recovery_generation=3, strategy_recovery_generation=3, trigger_kind='FULL_COHORT_STALL', recovery_started_wall_ms=1000, strategy_since_wall_ms=1000, now_wall_ms=12001, filter_mode='UNFILTERED', hardware_filter_count=0, expected_valid=False),
'generation-mismatch.json': dict(strategy='UNFILTERED_RECOVERY', active_recovery_generation=4, strategy_recovery_generation=3, trigger_kind='PEER_STARVATION', recovery_started_wall_ms=1000, strategy_since_wall_ms=1000, now_wall_ms=2000, filter_mode='UNFILTERED', hardware_filter_count=0, expected_valid=False),
'primary-without-filter.json': dict(strategy='FILTERED_PRIMARY', active_recovery_generation=None, strategy_recovery_generation=None, trigger_kind=None, recovery_started_wall_ms=None, strategy_since_wall_ms=1000, now_wall_ms=2000, filter_mode='UNFILTERED', hardware_filter_count=0, expected_valid=False),
'probe-without-provenance.json': dict(strategy='FILTERED_RECOVERY_PROBE', active_recovery_generation=None, strategy_recovery_generation=None, trigger_kind=None, recovery_started_wall_ms=None, strategy_since_wall_ms=1000, now_wall_ms=2000, filter_mode='MANUFACTURER_FILTERED', hardware_filter_count=1, expected_valid=False),
'unknown-state.json': dict(strategy='COOLDOWN', active_recovery_generation=2, strategy_recovery_generation=None, trigger_kind='FULL_COHORT_STALL', recovery_started_wall_ms=None, strategy_since_wall_ms=1000, now_wall_ms=2000, filter_mode='MANUFACTURER_FILTERED', hardware_filter_count=1, expected_valid=False),
}
for name, data in fixtures.items():
    write('validation/fixtures/dev13/' + name, json.dumps(data, indent=2) + '\n')

# ---- Validators -------------------------------------------------------------
write('validation/analysis/validate_environment_authorization.py', r'''#!/usr/bin/env python3
import json, sys
from pathlib import Path

UNFILTERED_WINDOW_MS=10000
PROBE_WINDOW_MS=15000
TRIGGERS={'FULL_COHORT_STALL','PEER_STARVATION'}

def evaluate(c):
    s=c.get('strategy'); mode=c.get('filter_mode'); count=c.get('hardware_filter_count',0)
    if s=='FILTERED_PRIMARY': return mode=='MANUFACTURER_FILTERED' and count>0
    if s=='UNFILTERED_RECOVERY':
        g=c.get('active_recovery_generation'); sg=c.get('strategy_recovery_generation'); started=c.get('recovery_started_wall_ms')
        return g is not None and sg is not None and g==sg and c.get('trigger_kind') in TRIGGERS and started is not None and c.get('now_wall_ms',0)-started<=UNFILTERED_WINDOW_MS and mode=='UNFILTERED' and count==0
    if s=='FILTERED_RECOVERY_PROBE':
        g=c.get('active_recovery_generation'); sg=c.get('strategy_recovery_generation')
        return g is not None and sg is not None and g==sg and c.get('trigger_kind') in TRIGGERS and c.get('now_wall_ms',0)-c.get('strategy_since_wall_ms',0)<=PROBE_WINDOW_MS and mode=='MANUFACTURER_FILTERED' and count>0
    return False

def main(paths):
    if not paths: paths=sorted(str(p) for p in Path('validation/fixtures/dev13').glob('*.json'))
    results=[]; ok=True
    for path in paths:
        d=json.load(open(path)); actual=evaluate(d); expected=d.get('expected_valid') is True; passed=actual==expected; ok &= passed
        results.append({'file':path,'expected_valid':expected,'actual_valid':actual,'pass':passed})
    print(json.dumps({'results':results,'pass':ok},indent=2)); return 0 if ok else 1
if __name__=='__main__': raise SystemExit(main(sys.argv[1:]))
''')
write('validation/analysis/validate_preflight_snapshot.py', r'''#!/usr/bin/env python3
import json,sys
p=sys.argv[1]; d=json.load(open(p)); r=d.get('validation_run',d); q=r.get('preflight_at_start') or {}
checks={
 'ready':q.get('ready') is True,
 'bluetooth_on':q.get('bluetooth_on') is True,
 'ble_permissions_ready':q.get('ble_permissions_ready') is True,
 'battery_saver_off':q.get('battery_saver_off') is True,
 'screen_on':q.get('screen_on') is True,
 'app_foreground':q.get('app_foreground') is True,
 'foreground_service_running':q.get('foreground_service_running') is True,
 'ble_scanner_running':q.get('ble_scanner_running') is True,
 'expected_ble_peer_count>=2':q.get('expected_ble_peer_count',0)>=2,
 'strategy_primary':q.get('acquisition_strategy')=='FILTERED_PRIMARY',
 'filter_mode':q.get('filter_mode')=='MANUFACTURER_FILTERED',
 'hardware_filter_count>0':q.get('hardware_filter_count',0)>0,
 'blocking_reasons_empty':not q.get('blocking_reasons'),
}
ok=all(checks.values()); print(json.dumps({'file':p,'checks':checks,'pass':ok},indent=2)); sys.exit(0 if ok else 1)
''')
write('validation/analysis/validate_dev13_hard_gates.py', r'''#!/usr/bin/env python3
import json,sys
p=sys.argv[1]; d=json.load(open(p)); r=d.get('validation_run',d); env=r.get('environment') or {}; pf=r.get('preflight_at_start') or {}
checks={
 'snapshot_schema_version=3':r.get('snapshot_schema_version')==3,
 'snapshot_frozen':r.get('snapshot_frozen') is True,
 'elapsed_ms>=300000':r.get('elapsed_ms',0)>=300000,
 'acceptance_duration_eligible':r.get('acceptance_duration_eligible') is True,
 'short_diagnostic_run=false':r.get('short_diagnostic_run') is False,
 'preflight_ready':pf.get('ready') is True,
 'preflight_primary':pf.get('acquisition_strategy')=='FILTERED_PRIMARY',
 'preflight_filtered':pf.get('filter_mode')=='MANUFACTURER_FILTERED' and pf.get('hardware_filter_count',0)>0,
 'environment_valid':r.get('environment_valid') is True and env.get('valid') is True,
 'no_unauthorized_strategy':env.get('unauthorized_strategy_violation_count',0)==0,
 'no_false_not_filtered_primary':'NOT_FILTERED_PRIMARY' not in (r.get('environment_violation_types') or []) and 'NOT_FILTERED_PRIMARY' not in (env.get('violation_types') or []),
 'usable_metric>=90':(r.get('usable_metric_range_uptime_percent') or 0)>=90,
 'geometry_2d>=90':(r.get('geometry_2d_uptime_percent') or 0)>=90,
 'peer_expire_delta=0':r.get('peer_expire_delta')==0,
 'recovery_attempt_delta<=3':r.get('recovery_attempt_delta',99)<=3,
 'manual_geometry_override=false':d.get('manual_geometry_override') is False,
 'human_scanning=false':d.get('human_scanning_enabled') is False,
 'human_localization=false':d.get('human_localization_validated') is False,
 'rescue_use=false':d.get('rescue_use_validated') is False,
}
ok=all(checks.values()); print(json.dumps({'file':p,'checks':checks,'pass':ok},indent=2)); sys.exit(0 if ok else 1)
''')
write('validation/analysis/build_acceptance_report.py', r'''#!/usr/bin/env python3
import argparse,json,sys
from pathlib import Path
ap=argparse.ArgumentParser(); ap.add_argument('--device',action='append',default=[]); ap.add_argument('--out',default='acceptance_report.json'); ap.add_argument('--md',default=None); a=ap.parse_args()
result={'release':'dev-13','devices':{},'pass':True,'screenshots_required':False}
for spec in a.device:
 name,path=spec.split('=',1); d=json.load(open(path)); r=d.get('validation_run',d); env=r.get('environment') or {}; pf=r.get('preflight_at_start') or {}
 checks={'snapshot_frozen':r.get('snapshot_frozen') is True,'schema_v3':r.get('snapshot_schema_version')==3,'elapsed':r.get('elapsed_ms',0)>=300000,'duration_eligible':r.get('acceptance_duration_eligible') is True,'short_false':r.get('short_diagnostic_run') is False,'preflight':pf.get('ready') is True and pf.get('acquisition_strategy')=='FILTERED_PRIMARY' and pf.get('hardware_filter_count',0)>0,'usable_metric':(r.get('usable_metric_range_uptime_percent') or 0)>=90,'geometry_2d':(r.get('geometry_2d_uptime_percent') or 0)>=90,'peer_expire':r.get('peer_expire_delta')==0,'recovery_budget':r.get('recovery_attempt_delta',99)<=3,'environment':r.get('environment_valid') is True and env.get('valid') is True,'unauthorized_strategy':env.get('unauthorized_strategy_violation_count',0)==0}
 passed=all(checks.values()); result['devices'][name]={'checks':checks,'pass':passed}; result['pass'] &= passed
Path(a.out).write_text(json.dumps(result,indent=2)+'\n')
md=Path(a.md or str(Path(a.out).with_suffix('.md'))); lines=['# dev-13 acceptance report','',f"Overall: **{'PASS' if result['pass'] else 'FAIL'}**",'', '| Device | Result |','|---|---|']
for name,v in result['devices'].items(): lines.append(f"| {name} | {'PASS' if v['pass'] else 'FAIL'} |")
lines += ['', 'Evidence is JSON-based; screenshots are not required.']; md.write_text('\n'.join(lines)+'\n')
print(json.dumps(result,indent=2)); sys.exit(0 if result['pass'] else 1)
''')

# contract check
write('validation/android/check_dev13_environment_contract.py', r'''#!/usr/bin/env python3
from pathlib import Path
import subprocess,sys
root=Path(__file__).resolve().parents[2]
n=(root/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt').read_text()
b=(root/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleAcquisitionPolicy.kt').read_text()
e=(root/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/EnvironmentStrategyValidator.kt').read_text()
v=(root/'apps/mobile/src/version.ts').read_text()
required=[
 ('version','0.2.0-experimental.13' in v and 'reportVersion: 15' in v and 'snapshotSchemaVersion: 3' in v),
 ('strict preflight','START_REQUIRES_FILTERED_PRIMARY' in n and 'preflight_at_start' in n),
 ('runtime authorized recovery','AUTHORIZED_BOUNDED_RECOVERY_GENERATION' in e and 'AUTHORIZED_FILTERED_RECOVERY_PROBE' in e),
 ('unauthorized rejected','UNFILTERED_RECOVERY_WITHOUT_GENERATION' in e and 'RECOVERY_GENERATION_MISMATCH' in e),
 ('env counters','authorized_strategy_transition_count' in n and 'unauthorized_strategy_violation_count' in n),
 ('generation provenance','strategyRecoveryGeneration' in b and 'strategy_recovery_generation' in b),
 ('old false rule removed','currentStrategy() != BleAcquisitionStrategy.FILTERED_PRIMARY) issues += "NOT_FILTERED_PRIMARY"' not in n),
]
for name,ok in required:
 print(f"{name}: {'PASS' if ok else 'FAIL'}")
 if not ok: sys.exit(1)
subprocess.run([sys.executable,str(root/'validation/analysis/validate_environment_authorization.py')],cwd=root,check=True)
print('dev13 environment contract: PASS')
''')

# migrate version-sensitive inherited checks, keep historical named contracts untouched
for fp in p('validation/android').glob('check_*.py'):
    if fp.name in {'check_dev11_frozen_truth_contract.py','check_dev12_peer_starvation_contract.py','check_dev13_environment_contract.py'}:
        continue
    s=fp.read_text()
    for old,new in [
        ('0.2.0-experimental.12','0.2.0-experimental.13'),
        ('Experimental.12','Experimental.13'),
        ('experimental.12','experimental.13'),
        ('dev12 version truth missing','dev13 version truth missing'),
        ('reportVersion: 14','reportVersion: 15'),
        ("versionCode']==12","versionCode']==13"),
        ("versionCode'] == 12","versionCode'] == 13"),
        ('versionCode must be 12','versionCode must be 13'),
        ('versionCode is 12','versionCode is 13'),
        ('snapshotSchemaVersion: 2','snapshotSchemaVersion: 3'),
    ]: s=s.replace(old,new)
    fp.write_text(s)

# ---- Frozen truth and testing instructions ---------------------------------
write('DEV13_FROZEN_TRUTH.md', '''# dev-13 frozen truth

Protocol remains 2. BLE physics remain unchanged: profile `android-ble-lab-v1`; RSSI@1m=-69.19 dBm; n=3.62; domain=0.5–5.0 m; minSamples=3; fresh=5000 ms; holdover/hard-expiry=10000 ms; sigma aging=0.15 m/s; peer starvation=6000 ms; cohort stall=5000 ms; recovery<=3/rolling 5 min; cooldown=30000 ms; API36 BLE yield=120000 ms; automatic geometry and reciprocal fusion unchanged.

Startup requires FILTERED_PRIMARY + MANUFACTURER_FILTERED + hardware_filter_count>0. Runtime UNFILTERED_RECOVERY/FILTERED_RECOVERY_PROBE is valid only with matching bounded recovery-generation provenance. Human scanning/localization/rescue remain disabled. Acceptance evidence is JSON-only; screenshots are not required.
''')
write('docs/TESTING_DEV13.md', '''# TESTING_DEV13

No screenshots are required. Every test artifact must produce/share JSON or JSONL containing its own diagnostic truth.

## 1. Verify release
Download all assets from `dev-13`, then:

```bash
sha256sum --check SHA256SUMS.txt
python3 -m json.tool release-verification.json >/dev/null
python3 validation-kit/validate_release_manifest.py release-manifest.json
```

Use the same `body-finder-ruview-universal.apk` on Pixel 10 Pro, Pixel 7 Pro and Lenovo TB-J606L.

## 2. Three-Android acceptance
1. Put the three devices stationary in a non-collinear triangle, each pair 0.5–5.0 m. Record tape distances in `ground-truth-template.json` only; never enter coordinates into the app.
2. Bluetooth ON, Battery Saver OFF, screen ON, app foreground, same session. Wait until each shows >=2 BLE peers and preflight `ready=true`.
3. Start Validation on all three; keep stationary >=330 s; End Validation.
4. Export the selected long run from each device as `*_run_long_export1.json`.
5. Leave apps alive >=180 s without starting another run; export the same long run as `*_run_long_export2.json`.
6. On each device create one short run <300 s; then reselect the original long run and export `*_run_long_after_short_run.json`.
7. Run:

```bash
unzip validators-dev13.zip -d validation-kit
python3 validation-kit/validate_dev13_hard_gates.py pixel10_run_long_export1.json
python3 validation-kit/validate_dev13_hard_gates.py pixel7_run_long_export1.json
python3 validation-kit/validate_dev13_hard_gates.py lenovo_run_long_export1.json
python3 validation-kit/validate_snapshot_immutability.py pixel10_run_long_export1.json pixel10_run_long_export2.json pixel10_run_long_after_short_run.json
python3 validation-kit/validate_snapshot_immutability.py pixel7_run_long_export1.json pixel7_run_long_export2.json pixel7_run_long_after_short_run.json
python3 validation-kit/validate_snapshot_immutability.py lenovo_run_long_export1.json lenovo_run_long_export2.json lenovo_run_long_after_short_run.json
python3 validation-kit/validate_preflight_snapshot.py pixel10_run_long_export1.json
python3 validation-kit/validate_environment_authorization.py
python3 validation-kit/build_acceptance_report.py --device pixel10=pixel10_run_long_export1.json --device pixel7=pixel7_run_long_export1.json --device lenovo=lenovo_run_long_export1.json --out acceptance_report.json --md acceptance_report.md
python3 validation-kit/calculate_accuracy_report.py --ground-truth ground-truth-template.json --export pixel10_run_long_export1.json --export pixel7_run_long_export1.json --export lenovo_run_long_export1.json > accuracy_report.json
```

PASS requires 3/3 frozen schema-v3 snapshots, >=300 s, `environment_valid=true`, preflight primary/filtered, usable metric and Geometry2D >=90%, peer expiry=0, recovery attempts<=3, unauthorized strategy violations=0, plus the recovery/timeline/geometry validators.

## 3. Ubuntu / WSL
Extract the Linux tarball (or install the `.deb`) and run:

```bash
./body-finder-node --node ubuntu --session body-finder-lab --calibrate 10 --record ubuntu-node.jsonl
```

On WSL use the same Linux binary. Stop with Ctrl+C. `ubuntu-node.jsonl` is the evidence: each line includes build/release, capabilities, geometry state, safety flags and self-diagnostic fields.

## 4. Windows
Extract `body-finder-node-windows-x86_64.zip` and run PowerShell:

```powershell
.\\body-finder-node.exe --node windows --session body-finder-lab --calibrate 10 --record windows-node.jsonl
```

`windows-node.jsonl` is the complete evidence; no screenshot is needed.

## 5. iOS simulator
Unzip `body-finder-ruview-ios-simulator.zip`, install/launch the `.app` in an iOS Simulator and confirm it starts. This is a build/smoke artifact; the physical BLE acceptance gate is Android.

Return the nine Android JSON exports, filled ground-truth JSON, `acceptance_report.json`, `acceptance_report.md`, `accuracy_report.json`, plus Linux/WSL/Windows JSONL when those artifacts are tested.
''')

# ---- Node artifacts emit self-diagnostic JSONL ------------------------------
node_rel='apps/node/src/main.rs'; node=read(node_rel)
node=node.replace(
'''            "type":"status",\n            "unix_ms":now_ms,''',
'''            "type":"status",\n            "release":"dev-13",\n            "build":"0.2.0-experimental.13",\n            "report_version":15,\n            "protocol_version":PROTOCOL_VERSION,\n            "evidence_contract":{"schema":"dev13-node-jsonl-evidence-v1","screenshots_required":false,"json_self_contained":true,"record_flag":"--record FILE.jsonl"},\n            "self_diagnostic":{"platform":platform,"udp_bound":true,"automatic_geometry":true,"manual_geometry_override":false,"human_scanning_enabled":false,"human_localization_validated":false,"rescue_use_validated":false},\n            "unix_ms":now_ms,''')
write(node_rel,node)

# ---- Release workflow: transform known-good dev12 matrix --------------------
w=read('.github/workflows/release-exp12.yml')
repls=[
('Dev Release experimental.12','Dev Release experimental.13'),('RELEASE_DEV12_TRIGGER.txt','RELEASE_DEV13_TRIGGER.txt'),('release-exp12','release-exp13'),('exp12','exp13'),('experimental.12','experimental.13'),('Experimental.12','Experimental.13'),('experimental12','experimental13'),('dev-12','dev-13'),('dev12','dev13'),('DEV12','DEV13'),('reportVersion: 14','reportVersion: 15'),('"versionCode": 12','"versionCode": 13'),('snapshotSchemaVersion: 2','snapshotSchemaVersion: 3'),('validation-run-snapshot-v2','validation-run-snapshot-v3'),('snapshot-v2','snapshot-v3'),('"schema_version": 12','"schema_version": 13'),('"report_version": 14','"report_version": 15'),('"validation_snapshot_schema_version": 2','"validation_snapshot_schema_version": 3'),
]
for old,new in repls: w=w.replace(old,new)
# restore historical no-regression checker that global dev12 changed
w=w.replace('check_dev13_peer_starvation_contract.py','check_dev12_peer_starvation_contract.py')
# requirements: add new validators/contracts if absent
anchor='          python3 validation/android/check_dev12_peer_starvation_contract.py\n'
addition='''          python3 validation/android/check_dev12_peer_starvation_contract.py\n          python3 validation/android/check_dev13_environment_contract.py\n          python3 validation/analysis/validate_environment_authorization.py\n'''
if anchor in w: w=w.replace(anchor,addition,1)
# extend compile set
w=w.replace('validation/analysis/validate_dev13_hard_gates.py ', 'validation/analysis/validate_dev13_hard_gates.py validation/analysis/validate_environment_authorization.py validation/analysis/validate_preflight_snapshot.py ')
# package new validators explicitly
w=w.replace('cp validation/analysis/validate_dev13_hard_gates.py ', 'cp validation/analysis/validate_dev13_hard_gates.py validation/analysis/validate_environment_authorization.py validation/analysis/validate_preflight_snapshot.py ')
# canonical lock filename only
w=w.replace('ruvview-upstream-lock.json','ruview-upstream-lock.json')
# mandatory contract enrich release manifest after existing json evidence line
w=w.replace(
'''            "json_evidence_self_contained": true,\n            "screenshots_required_for_acceptance": false,''',
'''            "json_evidence_self_contained": true,\n            "screenshots_required_for_acceptance": false,\n            "environment_validation_recovery_aware": true,\n            "preflight_at_start_frozen": true,\n            "authorized_strategy_transition_telemetry": true,\n            "unauthorized_strategy_detection": true,''')
# release notes concise truth
w=w.replace('dev-13 adds persistent per-peer BLE starvation detection and targeted recovery while preserving the frozen coarse BLE physics and the single shared recovery budget. Recovery success for PEER_STARVATION requires a valid callback from the target peer.', 'dev-13 fixes validation/environment semantics: bounded arbiter-owned recovery is authorized, while uncontrolled unfiltered/probe states remain invalid. It freezes preflight_at_start and preserves all dev-12 BLE/recovery/geometry invariants.')
w=w.replace('Evidence is JSON-only: screenshots are not required. Each Android export contains the validation preflight, environment truth, per-peer health/starvation state, recovery trigger/generation/target causality, system-ranging state, frozen geometry/fusion/graph diagnostics and self-diagnostic hard-gate results.', 'Evidence is JSON-only: screenshots are not required. Android exports include frozen preflight, recovery-generation authorization, environment counters/timeline, per-peer causality, system ranging, frozen geometry/fusion/graph diagnostics and hard-gate truth; node binaries emit diagnostic JSONL.')
write('.github/workflows/release-exp13.yml',w)

# ---- Bootstrap workflow -----------------------------------------------------
write('.github/workflows/bootstrap-dev13.yml', '''name: Dev13 environment integrity bootstrap

on:
  push:
    branches: [main]
    paths: ['DEV13_BOOTSTRAP_TRIGGER.txt']
  workflow_dispatch:

permissions:
  contents: write

jobs:
  apply:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { ref: main, fetch-depth: 0 }
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - name: Apply dev13 plan
        run: python3 scripts/apply_dev13.py
      - name: Validate source and deterministic gates
        shell: bash
        run: |
          set -euxo pipefail
          python3 -m py_compile validation/analysis/validate_dev13_hard_gates.py validation/analysis/validate_environment_authorization.py validation/analysis/validate_preflight_snapshot.py validation/analysis/build_acceptance_report.py
          python3 validation/analysis/validate_environment_authorization.py
          python3 validation/android/check_dev13_environment_contract.py
          python3 -m json.tool protocol/schemas/validation-run-snapshot-v3.json >/dev/null
          cargo test --workspace
          test -s docs/TESTING_DEV13.md
          grep -qi 'No screenshots are required' docs/TESTING_DEV13.md
      - name: Commit dev13 implementation
        shell: bash
        run: |
          set -euxo pipefail
          git config user.name github-actions[bot]
          git config user.email 41898282+github-actions[bot]@users.noreply.github.com
          git add apps crates validation protocol docs DEV13_FROZEN_TRUTH.md .github/workflows/release-exp13.yml scripts/apply_dev13.py
          if ! git diff --cached --quiet; then
            git commit -m 'feat: implement dev13 recovery-aware environment integrity'
            git push origin HEAD:main
          fi
      - name: Trigger dev13 release after workflow is committed
        shell: bash
        run: |
          set -euxo pipefail
          git pull --ff-only origin main
          printf 'dev13 release trigger %s\\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > RELEASE_DEV13_TRIGGER.txt
          git add RELEASE_DEV13_TRIGGER.txt
          git commit -m 'ci: trigger dev13 full release matrix'
          git push origin HEAD:main
''')

print('dev13 source patch applied successfully')
