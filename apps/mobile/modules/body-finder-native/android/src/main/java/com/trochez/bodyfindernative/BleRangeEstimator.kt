package com.trochez.bodyfindernative

import org.json.JSONObject
import kotlin.math.abs
import kotlin.math.ln
import kotlin.math.max
import kotlin.math.pow
import kotlin.math.sqrt

@JvmInline
internal value class RssiDbm(val value: Double)

@JvmInline
internal value class TransmitPowerDbm(val value: Double)

@JvmInline
internal value class RssiAtOneMeterDbm(val value: Double)

@JvmInline
internal value class PathLossExponent(val value: Double)

@JvmInline
internal value class DistanceMeters(val value: Double)

internal data class BleRangeCalibrationProfile(
  val schemaVersion: Int,
  val profileId: String,
  val source: String,
  val rssiAtOneMeter: RssiAtOneMeterDbm,
  val rssiAtOneMeterSigmaDb: Double,
  val pathLossExponent: PathLossExponent,
  val pathLossExponentSigma: Double,
  val validDistanceMinM: Double,
  val validDistanceMaxM: Double,
  val environment: String,
  val sampleCount: Int,
  val validated: Boolean,
  val validationNote: String,
) {
  fun toJson(): JSONObject = JSONObject()
    .put("schema_version", schemaVersion)
    .put("profile_id", profileId)
    .put("source", source)
    .put("rssi_at_1m_dbm", rssiAtOneMeter.value)
    .put("rssi_at_1m_sigma_db", rssiAtOneMeterSigmaDb)
    .put("path_loss_exponent", pathLossExponent.value)
    .put("path_loss_exponent_sigma", pathLossExponentSigma)
    .put("valid_distance_min_m", validDistanceMinM)
    .put("valid_distance_max_m", validDistanceMaxM)
    .put("environment", environment)
    .put("sample_count", sampleCount)
    .put("validated", validated)
    .put("validation_note", validationNote)
}

internal enum class BleRangeStatus {
  VALID,
  PROXIMITY_ONLY,
  UNCALIBRATED,
  SATURATED_LOW,
  SATURATED_HIGH,
  INSUFFICIENT_SAMPLES,
  STALE,
  NONFINITE,
  OUT_OF_MODEL_DOMAIN,
}

internal data class BleRangeEstimate(
  val status: BleRangeStatus,
  val distanceM: Double?,
  val sigmaM: Double?,
  val rawDistanceM: Double?,
  val medianRssiDbm: Double?,
  val medianAdvertisedTxPowerDbm: Double?,
  val sampleCount: Int,
  val profileId: String,
  val calibrationState: String,
  val proximityBand: String?,
  val metricValid: Boolean,
  val detail: String,
) {
  fun toJson(): JSONObject = JSONObject()
    .put("status", status.name)
    .put("distance_m", distanceM ?: JSONObject.NULL)
    .put("sigma_m", sigmaM ?: JSONObject.NULL)
    .put("raw_distance_m", rawDistanceM ?: JSONObject.NULL)
    .put("rssi_dbm", medianRssiDbm ?: JSONObject.NULL)
    .put("advertised_tx_power_dbm", medianAdvertisedTxPowerDbm ?: JSONObject.NULL)
    .put("sample_count", sampleCount)
    .put("calibration_profile_id", profileId)
    .put("calibration_state", calibrationState)
    .put("proximity_band", proximityBand ?: JSONObject.NULL)
    .put("metric_valid", metricValid)
    .put("detail", detail)
}

internal object BleRangeEstimator {
  /*
   * T2/T4b screening showed non-monotonic RSSI across the 1.18-3.50 m layout.
   * Therefore this profile is intentionally NOT validated for metric geometry.
   * It is used only to expose raw model estimates for calibration tooling.
   */
  val profile = BleRangeCalibrationProfile(
    schemaVersion = 1,
    profileId = "android-ble-screening-v1",
    source = "T2_T4B_SCREENING_PLUS_GENERIC_PRIOR",
    rssiAtOneMeter = RssiAtOneMeterDbm(-67.0),
    rssiAtOneMeterSigmaDb = 8.0,
    pathLossExponent = PathLossExponent(2.4),
    pathLossExponentSigma = 0.7,
    validDistanceMinM = 0.30,
    validDistanceMaxM = 12.0,
    environment = "INDOOR_OPEN_FIELD_SCREENING",
    sampleCount = 13,
    validated = false,
    validationNote = "T2/T4b single-layout RSSI observations overlap/invert across 1.18-3.50 m; metric BLE RSSI is withheld until a multi-distance calibration run passes.",
  )

  fun median(values: List<Double>): Double {
    require(values.isNotEmpty())
    val sorted = values.sorted()
    val n = sorted.size
    return if (n % 2 == 0) (sorted[n / 2 - 1] + sorted[n / 2]) / 2.0 else sorted[n / 2]
  }

  private fun validRssiSamples(values: List<Double>): List<Double> =
    values.filter { it.isFinite() && it in -127.0..20.0 }

  private fun mad(values: List<Double>, center: Double): Double =
    if (values.isEmpty()) 0.0 else median(values.map { abs(it - center) })

  private fun proximityBand(rssi: Double): String = when {
    rssi >= -60.0 -> "NEAR"
    rssi >= -72.0 -> "MID"
    rssi >= -84.0 -> "FAR"
    else -> "VERY_FAR"
  }

  fun estimate(
    rssiValues: List<Double>,
    advertisedTxPowerValues: List<Double>,
    minSamples: Int,
    activeProfile: BleRangeCalibrationProfile = profile,
  ): BleRangeEstimate {
    val validRssiValues = validRssiSamples(rssiValues)
    if (validRssiValues.size < minSamples) {
      return BleRangeEstimate(
        status = BleRangeStatus.INSUFFICIENT_SAMPLES,
        distanceM = null,
        sigmaM = null,
        rawDistanceM = null,
        medianRssiDbm = validRssiValues.takeIf { it.isNotEmpty() }?.let(::median),
        medianAdvertisedTxPowerDbm = advertisedTxPowerValues.takeIf { it.isNotEmpty() }?.let(::median),
        sampleCount = validRssiValues.size,
        profileId = activeProfile.profileId,
        calibrationState = if (activeProfile.validated) "CALIBRATED_COARSE" else "UNVALIDATED_SCREENING",
        proximityBand = validRssiValues.takeIf { it.isNotEmpty() }?.let(::median)?.let(::proximityBand),
        metricValid = false,
        detail = if (validRssiValues.size == rssiValues.size) {
          "Need at least $minSamples fresh RSSI samples"
        } else {
          "Need at least $minSamples fresh valid RSSI samples; invalid Android RSSI sentinel/out-of-domain values were ignored"
        },
      )
    }

    val rssi = median(validRssiValues)
    val tx = advertisedTxPowerValues.takeIf { it.isNotEmpty() }?.let(::median)
    val n = activeProfile.pathLossExponent.value
    val exponent = (activeProfile.rssiAtOneMeter.value - rssi) / (10.0 * n)
    val rawDistance = 10.0.pow(exponent)

    if (!rawDistance.isFinite() || rawDistance <= 0.0) {
      return BleRangeEstimate(
        BleRangeStatus.NONFINITE, null, null, rawDistance.takeIf { it.isFinite() },
        rssi, tx, validRssiValues.size, activeProfile.profileId,
        if (activeProfile.validated) "CALIBRATED_COARSE" else "UNVALIDATED_SCREENING",
        proximityBand(rssi), false, "Log-distance estimate is non-finite",
      )
    }

    val status = when {
      rawDistance < activeProfile.validDistanceMinM -> BleRangeStatus.SATURATED_LOW
      rawDistance > activeProfile.validDistanceMaxM -> BleRangeStatus.SATURATED_HIGH
      !activeProfile.validated -> BleRangeStatus.PROXIMITY_ONLY
      else -> BleRangeStatus.VALID
    }

    val metricValid = status == BleRangeStatus.VALID
    val distance = rawDistance.takeIf { metricValid }
    val rssiMadSigma = max(1.4826 * mad(validRssiValues, rssi), 1.0)
    val combinedRssiSigma = sqrt(
      rssiMadSigma * rssiMadSigma +
        activeProfile.rssiAtOneMeterSigmaDb * activeProfile.rssiAtOneMeterSigmaDb
    )
    val dRssi = rawDistance * ln(10.0) / (10.0 * n)
    val dN = rawDistance * ln(10.0) * abs(activeProfile.rssiAtOneMeter.value - rssi) /
      (10.0 * n * n)
    val propagated = sqrt(
      (dRssi * combinedRssiSigma) * (dRssi * combinedRssiSigma) +
        (dN * activeProfile.pathLossExponentSigma) * (dN * activeProfile.pathLossExponentSigma)
    )
    val sigma = max(1.0, max(rawDistance * 0.50, propagated)).takeIf { metricValid }

    val calibrationState = if (activeProfile.validated) "CALIBRATED_COARSE" else "UNVALIDATED_SCREENING"
    val detail = when (status) {
      BleRangeStatus.VALID ->
        "BLE RSSI metric estimate from validated profile ${activeProfile.profileId}; advertised TxPower is diagnostic only and is NOT used as RSSI@1m"
      BleRangeStatus.PROXIMITY_ONLY ->
        "BLE RSSI observed but profile ${activeProfile.profileId} is not validated for metric geometry; raw model estimate is diagnostic only"
      BleRangeStatus.SATURATED_LOW ->
        "Raw BLE RSSI estimate is below calibrated model domain; no metric distance emitted"
      BleRangeStatus.SATURATED_HIGH ->
        "Raw BLE RSSI estimate is above calibrated model domain; no metric distance emitted"
      else -> status.name
    }

    return BleRangeEstimate(
      status = status,
      distanceM = distance,
      sigmaM = sigma,
      rawDistanceM = rawDistance,
      medianRssiDbm = rssi,
      medianAdvertisedTxPowerDbm = tx,
      sampleCount = validRssiValues.size,
      profileId = activeProfile.profileId,
      calibrationState = calibrationState,
      proximityBand = proximityBand(rssi),
      metricValid = metricValid,
      detail = detail,
    )
  }
}
