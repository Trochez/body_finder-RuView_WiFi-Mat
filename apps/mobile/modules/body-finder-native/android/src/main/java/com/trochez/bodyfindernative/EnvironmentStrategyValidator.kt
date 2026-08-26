package com.trochez.bodyfindernative

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
      BleAcquisitionStrategy.FAILED_SAFE -> {
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
    }
  }
}
