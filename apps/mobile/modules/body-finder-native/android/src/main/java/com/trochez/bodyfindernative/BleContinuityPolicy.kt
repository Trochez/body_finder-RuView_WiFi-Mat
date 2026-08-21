package com.trochez.bodyfindernative

import kotlin.math.max
import kotlin.math.min

internal enum class BleRangeTemporalState {
  ACQUIRING,
  FRESH,
  HOLDOVER,
  STALE,
  EXPIRED,
  OUT_OF_DOMAIN,
  INVALID,
}

internal data class LastValidRangeState(
  val peerNodeId: String,
  val bleIdentity: String,
  val distanceM: Double,
  val sigmaM: Double,
  val rawDistanceM: Double?,
  val medianRssiDbm: Double?,
  val profileId: String,
  val calibrationState: String,
  val observationMonotonicNs: Long,
  val estimateWallMs: Long,
  val sourceDetail: String,
)

internal object BleContinuityPolicy {
  const val FRESH_MS = 5_000L
  const val HOLDOVER_MAX_MS = 10_000L
  const val HARD_EXPIRY_MS = 10_000L
  const val SIGMA_AGING_M_PER_S = 0.15
  const val HOLDOVER_SIGMA_CAP_M = 5.0

  fun holdoverEligible(lastValidAgeMs: Long?): Boolean =
    lastValidAgeMs != null && lastValidAgeMs in 0..HOLDOVER_MAX_MS

  fun temporalState(
    currentMetricValid: Boolean,
    explicitOutOfDomain: Boolean,
    explicitInvalid: Boolean,
    lastValidAgeMs: Long?,
  ): BleRangeTemporalState = when {
    explicitOutOfDomain -> BleRangeTemporalState.OUT_OF_DOMAIN
    explicitInvalid -> BleRangeTemporalState.INVALID
    currentMetricValid -> BleRangeTemporalState.FRESH
    lastValidAgeMs == null -> BleRangeTemporalState.ACQUIRING
    lastValidAgeMs <= HOLDOVER_MAX_MS -> BleRangeTemporalState.HOLDOVER
    lastValidAgeMs <= HARD_EXPIRY_MS -> BleRangeTemporalState.STALE
    else -> BleRangeTemporalState.EXPIRED
  }

  fun agedSigma(baseSigmaM: Double, lastValidAgeMs: Long): Double {
    val ageSeconds = max(0L, lastValidAgeMs).toDouble() / 1_000.0
    return min(HOLDOVER_SIGMA_CAP_M, max(baseSigmaM, baseSigmaM + SIGMA_AGING_M_PER_S * ageSeconds))
  }
}
