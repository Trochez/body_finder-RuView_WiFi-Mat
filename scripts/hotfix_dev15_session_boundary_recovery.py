#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt"
POLICY = ROOT / "apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleAcquisitionPolicy.kt"
ENV = ROOT / "apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/EnvironmentStrategyValidator.kt"
VALIDATOR = ROOT / "validation/analysis/dev15_validation.py"
DOCS = ROOT / "docs/TESTING_DEV15.md"
TRIGGER = ROOT / "RELEASE_DEV15_TRIGGER.txt"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f"patch anchor not found: {label}")
    return text.replace(old, new, 1)


# 1) Keep the frozen recovery budget/cooldown intact, but allow a completed run to
# establish a clean logical session boundary when the controller is in a filtered
# safety state. Active recovery/probe generations are never aborted.
policy = POLICY.read_text()
old = '''  @Synchronized
  fun markFailedSafe(now: Long, reason: String) {
    transition(BleAcquisitionStrategy.FAILED_SAFE, now, reason)
  }

  private fun isFiltered(s: BleAcquisitionStrategy): Boolean =
'''
new = '''  @Synchronized
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
'''
policy = replace_once(policy, old, new, "session boundary policy")

# 2) Complete the nested per-identity first-valid recovery counter that dev15
# declared but never incremented.
old = '''  fun snapshot(): BleAcquisitionCounterSnapshot = BleAcquisitionCounterSnapshot(
'''
new = '''  fun noteFirstValidRecovery(generation: Long, now: Long) {
    if (markGeneration(lastFirstValidRecoveryGeneration, generation)) {
      firstCallbackAfterRecoveryCount.incrementAndGet()
      val started = BleAcquisitionPolicy.recoveryStartedMs()
      if (started != null) lastRecoveryCallbackLatencyMs.set(max(0L, now - started))
    }
  }

  fun snapshot(): BleAcquisitionCounterSnapshot = BleAcquisitionCounterSnapshot(
'''
policy = replace_once(policy, old, new, "nested first-valid counter")
POLICY.write_text(policy)

# 3) FAILED_SAFE/COOLDOWN are filtered controller safety states, not user
# environment violations. Acceptance still rejects FAILED_SAFE_AT_END separately.
env = ENV.read_text()
old = '''      else -> StrategyEnvironmentDecision(false, false, "UNAUTHORIZED_ACQUISITION_STRATEGY", "RECOVERY_ARBITER_PROVENANCE_REQUIRED")
'''
new = '''      BleAcquisitionStrategy.FAILED_SAFE -> {
        if (c.filterMode == "MANUFACTURER_FILTERED" && c.hardwareFilterCount > 0) {
          StrategyEnvironmentDecision(true, true, null, "AUTHORIZED_FAILED_SAFE_RECOVERY_BUDGET_GUARD")
        } else {
          StrategyEnvironmentDecision(false, false, "FAILED_SAFE_FILTER_CONFIGURATION_INVALID", "FAILED_SAFE_REQUIRES_MANUFACTURER_FILTER")
        }
      }
      BleAcquisitionStrategy.COOLDOWN -> {
        if (c.filterMode == "MANUFACTURER_FILTERED" && c.hardwareFilterCount > 0) {
          StrategyEnvironmentDecision(true, true, null, "AUTHORIZED_FILTERED_COOLDOWN")
        } else {
          StrategyEnvironmentDecision(false, false, "COOLDOWN_FILTER_CONFIGURATION_INVALID", "COOLDOWN_REQUIRES_MANUFACTURER_FILTER")
        }
      }
'''
env = replace_once(env, old, new, "authorized filtered safety states")
ENV.write_text(env)

native = NATIVE.read_text()

# 4) Tie the legacy nested acquisition counter to the same exactly-once event.
old = '''    val validRssi = BleRangeEstimator.isValidBleRssi(result.rssi.toDouble())
    val callbackPeerId = peerIdForIdentity(id)
    if (validRssi && BleAcquisitionPolicy.currentStrategy() == BleAcquisitionStrategy.UNFILTERED_RECOVERY) {
      val acceptedFirstValid = BleAcquisitionPolicy.noteRecoveryFirstValidCallback(now, callbackPeerId)
      if (acceptedFirstValid && callbackPeerId != null && BleAcquisitionPolicy.activeRecoveryTriggerKind() == RecoveryTriggerKind.PEER_STARVATION) {
        FabricRuntime.peerStarvationRecoveryFirstValidByPeer.computeIfAbsent(callbackPeerId) { AtomicLong(0) }.incrementAndGet()
      }
    }
    FabricRuntime.acquisitionStatsByIdentity.computeIfAbsent(id) { BleAcquisitionStats() }.record(now, validRssi, BleAcquisitionPolicy.currentStrategy())
'''
new = '''    val validRssi = BleRangeEstimator.isValidBleRssi(result.rssi.toDouble())
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
'''
native = replace_once(native, old, new, "recordScan first-valid consistency")

# 5) A global scanner stall must not leave the logical recovery state running
# past its hard deadline, nor restart an unfiltered logical recovery as filtered
# while retaining UNFILTERED_RECOVERY provenance.
old = '''    if (global == GlobalBleScannerHealth.GLOBAL_SCANNER_STALLED) {
      if (now - FabricRuntime.lastScanRestartWallMs >= BleAcquisitionPolicy.MIN_RESTART_COOLDOWN_MS) {
        restartScannerWithStrategy(now, BleAcquisitionStrategy.FILTERED_PRIMARY, "GLOBAL_SCANNER_STALLED")
      }
      return
    }
'''
new = '''    if (global == GlobalBleScannerHealth.GLOBAL_SCANNER_STALLED) {
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
'''
native = replace_once(native, old, new, "global stall deadline handling")

# 6) After a completed run, if all physical preflight facts are currently good
# and only the filtered terminal controller state remains, normalize it before
# capturing the next run baseline. Do not bypass a missing peer or user/system
# environment problem.
old = '''    Function("startValidationRun") {
      val ctx = appContext.reactContext ?: return@Function "VALIDATION_ENVIRONMENT_INVALID:NO_CONTEXT"
      val now = System.currentTimeMillis()
      val preflight = validationPreflight(ctx, now)
      val blocking = preflight.optJSONArray("blocking_reasons") ?: JSONArray()
'''
new = '''    Function("startValidationRun") {
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
'''
native = replace_once(native, old, new, "start validation session boundary")
NATIVE.write_text(native)

# 7) Strict validation must distinguish an authorized safety state from a clean
# end-of-run state; a long snapshot ending FAILED_SAFE is still not a physical GO.
validator = VALIDATOR.read_text()
old = '''        acq = require_dict(run, "acquisition_state_at_end", "$.validation_run")
        if require_int(acq, "recovery_attempts_in_current_5min_window", "$.validation_run.acquisition_state_at_end") > 3: fail("G9", "RECOVERY_BUDGET_EXCEEDED")
        if require_int(acq, "filtered_probe_window_ms", "$.validation_run.acquisition_state_at_end") != 15000: fail("G13", "FILTERED_PROBE_HARD_LIMIT_DRIFT")
'''
new = '''        acq = require_dict(run, "acquisition_state_at_end", "$.validation_run")
        if require_int(acq, "recovery_attempts_in_current_5min_window", "$.validation_run.acquisition_state_at_end") > 3: fail("G9", "RECOVERY_BUDGET_EXCEEDED")
        if require_string(acq, "logical_acquisition_strategy", "$.validation_run.acquisition_state_at_end") == "FAILED_SAFE": fail("G9", "FAILED_SAFE_AT_END")
        if require_int(acq, "filtered_probe_window_ms", "$.validation_run.acquisition_state_at_end") != 15000: fail("G13", "FILTERED_PROBE_HARD_LIMIT_DRIFT")
'''
validator = replace_once(validator, old, new, "failed-safe hard gate")

old = '''        for peer_id, expected in peer_totals.items():
            if peer_id not in peer_index: fail("G12", f"RECOVERY_COUNTER_PEER_MISSING:{peer_id}"); continue
            fields = {"run_starvation_recovery_participation_count": expected["request"], "run_first_callback_after_recovery_count": expected["first"], "run_starvation_recovery_success_count": expected["success"], "run_starvation_recovery_failure_count": expected["failure"]}
            for key, wanted in fields.items():
                actual = require_int(peer_index[peer_id], key, f"$.validation_run.per_peer_at_end[{peer_id}]")
                if actual != wanted: fail("G12", f"RECOVERY_COUNTER_EVENT_MISMATCH:{peer_id}:{key}:{actual}!={wanted}")
'''
new = '''        all_first_by_peer = {}
        for event in require_list(run, "events", "$.validation_run"):
            if isinstance(event, dict) and event.get("type") == "FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY" and isinstance(event.get("peer_id"), str):
                all_first_by_peer[event["peer_id"]] = all_first_by_peer.get(event["peer_id"], 0) + 1
        for peer_id, expected in peer_totals.items():
            if peer_id not in peer_index: fail("G12", f"RECOVERY_COUNTER_PEER_MISSING:{peer_id}"); continue
            fields = {"run_starvation_recovery_participation_count": expected["request"], "run_first_callback_after_recovery_count": expected["first"], "run_starvation_recovery_success_count": expected["success"], "run_starvation_recovery_failure_count": expected["failure"]}
            for key, wanted in fields.items():
                actual = require_int(peer_index[peer_id], key, f"$.validation_run.per_peer_at_end[{peer_id}]")
                if actual != wanted: fail("G12", f"RECOVERY_COUNTER_EVENT_MISMATCH:{peer_id}:{key}:{actual}!={wanted}")
            nested = require_dict(peer_index[peer_id], "acquisition", f"$.validation_run.per_peer_at_end[{peer_id}]")
            nested_first = require_int(nested, "run_first_callback_after_recovery_count", f"$.validation_run.per_peer_at_end[{peer_id}].acquisition")
            wanted_nested_first = all_first_by_peer.get(peer_id, 0)
            if nested_first != wanted_nested_first: fail("G12", f"RECOVERY_COUNTER_EVENT_MISMATCH:{peer_id}:acquisition.run_first_callback_after_recovery_count:{nested_first}!={wanted_nested_first}")
'''
validator = replace_once(validator, old, new, "nested counter hard gate")
VALIDATOR.write_text(validator)

# 8) Keep the human procedure aligned with the actual boundary semantics.
docs = DOCS.read_text()
marker = "## Directed physical smoke"
if marker in docs and "session boundary" not in docs.lower():
    docs = docs.replace(
        marker,
        marker + "\n\nAfter each completed long export, the next short run must be startable without waiting for the rolling 5-minute recovery window to expire. The app normalizes only a completed-run `FAILED_SAFE`/`COOLDOWN` logical state back to `FILTERED_PRIMARY`; it does **not** clear the frozen 3-attempts/5-minute budget or 30-second cooldown. If the remote peer is actually absent, wait for `expected_ble_peer_count=1` before starting.\n",
        1,
    )
DOCS.write_text(docs)

TRIGGER.write_text("dev-15 session-boundary/recovery hotfix " + datetime.now(timezone.utc).isoformat() + "\n")
print("DEV15_SESSION_BOUNDARY_RECOVERY_HOTFIX_APPLIED")
