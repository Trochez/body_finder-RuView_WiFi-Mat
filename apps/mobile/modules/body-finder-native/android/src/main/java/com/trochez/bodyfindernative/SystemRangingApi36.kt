package com.trochez.bodyfindernative

import android.annotation.SuppressLint
import android.content.Context
import androidx.annotation.RequiresApi
import android.ranging.RangingData
import android.ranging.RangingDevice
import android.ranging.RangingManager
import android.ranging.RangingMeasurement
import android.ranging.RangingPreference
import android.ranging.RangingSession
import android.ranging.ble.rssi.BleRssiRangingParams
import android.ranging.raw.RawInitiatorRangingConfig
import android.ranging.raw.RawRangingDevice
import org.json.JSONObject
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicLong
import kotlin.math.max
import kotlin.math.min

/**
 * Android API-36+ precise/system ranging adapter.
 *
 * A real fresh platform range is preferred. Session-open events alone are NOT
 * success: only a real distance resets the failure/circuit state. Repeated
 * close/open churn with no result activates a bounded BLE-yield window so the
 * validated Body Finder BLE scanner/advertiser can use controller resources
 * without continuous RangingManager session recreation.
 */
@RequiresApi(36)
internal object SystemRangingApi36 {
  private const val RESULT_FRESHNESS_MS = 5_000L
  private const val BASE_RETRY_MS = 2_000L
  private const val MAX_RETRY_MS = 60_000L
  private const val CIRCUIT_BREAKER_FAILURES = 6
  private const val CIRCUIT_OPEN_MS = 60_000L

  data class Peer(val nodeId: String, val bluetoothAddress: String)

  data class Measurement(
    val peerNodeId: String,
    val monotonicNs: Long,
    val distanceM: Double?,
    val distanceSigmaM: Double?,
    val rssiDbm: Double?,
    val quality: String,
    val technology: String,
    val sourceDetail: String,
    val receivedWallMs: Long,
  )

  @Volatile var detail: String = "API36 RangingManager idle"
    private set
  @Volatile var sessionActive: Boolean = false
    private set
  @Volatile private var state: String = "IDLE"
  @Volatile private var requestedPeerCount: Int = 0
  @Volatile private var activePeerCount: Int = 0
  @Volatile private var lastResultWallMs: Long? = null
  @Volatile private var lastCloseReason: Int? = null
  @Volatile private var lastOpenFailureReason: Int? = null
  @Volatile private var lastError: String? = null
  @Volatile private var nextRetryWallMs: Long = 0
  @Volatile private var circuitOpenUntilWallMs: Long = 0
  @Volatile private var bleYieldUntilWallMs: Long = 0
  @Volatile private var bleYieldReason: String? = null
  @Volatile private var consecutiveFailures: Int = 0
  @Volatile private var closesSinceRealResult: Long = 0

  private var session: RangingSession? = null
  private var fingerprint: String = ""
  private val peerByUuid = ConcurrentHashMap<UUID, String>()
  private val resultCount = AtomicLong(0)
  private val openFailureCount = AtomicLong(0)
  private val closeFailureCount = AtomicLong(0)
  private val unexpectedFailureCount = AtomicLong(0)
  private val bleYieldCount = AtomicLong(0)
  val measurements = ConcurrentHashMap<String, Measurement>()

  fun hasFreshResult(now: Long = System.currentTimeMillis()): Boolean =
    measurements.values.any { it.distanceM != null && now - it.receivedWallMs <= RESULT_FRESHNESS_MS }

  fun isBleYieldActive(now: Long = System.currentTimeMillis()): Boolean = now < bleYieldUntilWallMs

  fun diagnostics(now: Long = System.currentTimeMillis()): JSONObject = JSONObject().apply {
    put("state", state)
    put("detail", detail)
    put("session_active", sessionActive)
    put("requested_peer_count", requestedPeerCount)
    put("active_peer_count", activePeerCount)
    put("result_count", resultCount.get())
    put("last_result_age_ms", lastResultWallMs?.let { max(0L, now - it) } ?: JSONObject.NULL)
    put("last_close_reason", lastCloseReason ?: JSONObject.NULL)
    put("last_open_failure_reason", lastOpenFailureReason ?: JSONObject.NULL)
    put("last_error", lastError ?: JSONObject.NULL)
    put("consecutive_failures", consecutiveFailures)
    put("open_failure_count", openFailureCount.get())
    put("close_failure_count", closeFailureCount.get())
    put("unexpected_failure_count", unexpectedFailureCount.get())
    put("closes_since_real_result", closesSinceRealResult)
    put("retry_in_ms", max(0L, nextRetryWallMs - now))
    put("circuit_open_in_ms", max(0L, circuitOpenUntilWallMs - now))
    put("fresh_result_available", hasFreshResult(now))
    put("ble_yield_active", isBleYieldActive(now))
    put("ble_yield_in_ms", max(0L, bleYieldUntilWallMs - now))
    put("ble_yield_count", bleYieldCount.get())
    put("ble_yield_reason", bleYieldReason ?: JSONObject.NULL)
    put("ble_yield_duration_ms", BleAcquisitionPolicy.SYSTEM_RANGING_BLE_YIELD_MS)
  }

  @SuppressLint("MissingPermission")
  fun stop() {
    closeSessionOnly()
    measurements.clear()
    resultCount.set(0)
    openFailureCount.set(0)
    closeFailureCount.set(0)
    unexpectedFailureCount.set(0)
    bleYieldCount.set(0)
    requestedPeerCount = 0
    activePeerCount = 0
    lastResultWallMs = null
    lastCloseReason = null
    lastOpenFailureReason = null
    lastError = null
    nextRetryWallMs = 0
    circuitOpenUntilWallMs = 0
    bleYieldUntilWallMs = 0
    bleYieldReason = null
    consecutiveFailures = 0
    closesSinceRealResult = 0
    state = "IDLE"
    detail = "API36 RangingManager idle"
  }

  private fun activateBleYield(now: Long, reason: String) {
    if (now >= bleYieldUntilWallMs) bleYieldCount.incrementAndGet()
    bleYieldUntilWallMs = max(bleYieldUntilWallMs, now + BleAcquisitionPolicy.SYSTEM_RANGING_BLE_YIELD_MS)
    bleYieldReason = reason
    state = "BLE_ACQUISITION_YIELD"
    detail = "API36 RangingManager yielding for validated BLE acquisition: $reason; real fresh system ranges remain preferred when available"
  }

  private fun registerFailure(now: Long, kind: String) {
    consecutiveFailures++
    val exponent = (consecutiveFailures - 1).coerceIn(0, 5)
    val backoff = min(MAX_RETRY_MS, BASE_RETRY_MS * (1L shl exponent))
    nextRetryWallMs = now + backoff
    if (consecutiveFailures >= CIRCUIT_BREAKER_FAILURES) {
      circuitOpenUntilWallMs = now + CIRCUIT_OPEN_MS
      state = "CIRCUIT_OPEN"
      detail = "API36 RangingManager circuit open after $consecutiveFailures consecutive failures ($kind); independent BLE evidence remains active"
    }
  }

  /** Only a real platform distance is a success. */
  private fun registerRealRangeSuccess() {
    consecutiveFailures = 0
    nextRetryWallMs = 0
    circuitOpenUntilWallMs = 0
    bleYieldUntilWallMs = 0
    bleYieldReason = null
    closesSinceRealResult = 0
    lastError = null
  }

  @SuppressLint("MissingPermission")
  fun refresh(context: Context, peers: List<Peer>) {
    val now = System.currentTimeMillis()
    val normalized = peers
      .filter { it.nodeId.isNotBlank() && it.bluetoothAddress.matches(Regex("([0-9A-F]{2}:){5}[0-9A-F]{2}")) }
      .distinctBy { it.nodeId }
      .sortedBy { it.nodeId }
    requestedPeerCount = normalized.size
    val nextFingerprint = normalized.joinToString("|") { "${it.nodeId}@${it.bluetoothAddress}" }

    if (normalized.isEmpty()) {
      if (session != null) closeSessionOnly()
      state = "READY_NO_BOUND_PEER"
      detail = "API36 RangingManager ready; awaiting a Body Finder BLE peer/address binding"
      return
    }
    if (hasFreshResult(now)) {
      // Do not tear down a valid live session; fresh system range remains preferred.
      if (nextFingerprint == fingerprint && session != null) return
    }
    if (nextFingerprint == fingerprint && session != null) return
    if (isBleYieldActive(now)) {
      state = "BLE_ACQUISITION_YIELD"
      detail = "API36 RangingManager BLE acquisition yield active; independent validated BLE scanning remains available"
      return
    }
    if (now < circuitOpenUntilWallMs) {
      state = "CIRCUIT_OPEN"
      detail = "API36 RangingManager circuit breaker active; independent BLE evidence remains available"
      return
    }
    if (now < nextRetryWallMs) {
      state = "BACKOFF"
      detail = "API36 RangingManager bounded retry backoff active; independent BLE evidence remains available"
      return
    }

    closeSessionOnly()
    requestedPeerCount = normalized.size
    try {
      val manager = context.getSystemService(RangingManager::class.java)
      if (manager == null) {
        state = "UNSUPPORTED"
        detail = "API36 RangingManager service unavailable"
        return
      }

      val configBuilder = RawInitiatorRangingConfig.Builder()
      for (peer in normalized) {
        val uuid = UUID.nameUUIDFromBytes(("body-finder-v2:${peer.nodeId}").toByteArray(Charsets.UTF_8))
        peerByUuid[uuid] = peer.nodeId
        val rangingDevice = RangingDevice.Builder().setUuid(uuid).build()
        val bleParams = BleRssiRangingParams.Builder(peer.bluetoothAddress)
          .setRangingUpdateRate(RawRangingDevice.UPDATE_RATE_NORMAL)
          .build()
        val rawDevice = RawRangingDevice.Builder()
          .setRangingDevice(rangingDevice)
          .setBleRssiRangingParams(bleParams)
          .build()
        configBuilder.addRawRangingDevice(rawDevice)
      }
      val preference = RangingPreference.Builder(
        RangingPreference.DEVICE_ROLE_INITIATOR,
        configBuilder.build(),
      ).build()

      val callback = object : RangingSession.Callback {
        override fun onOpened() {
          sessionActive = true
          activePeerCount = normalized.size
          state = "ACTIVE_NO_RESULT"
          detail = "API36 RangingManager raw BLE-RSSI session opened for ${normalized.size} peer(s); awaiting a real distance before declaring success"
        }

        override fun onOpenFailed(reason: Int) {
          val failureNow = System.currentTimeMillis()
          sessionActive = false
          activePeerCount = 0
          lastOpenFailureReason = reason
          openFailureCount.incrementAndGet()
          state = "OPEN_FAILED"
          detail = "API36 RangingManager session open failed reason=$reason; independent BLE evidence remains active"
          session = null
          fingerprint = ""
          peerByUuid.clear()
          registerFailure(failureNow, "open reason=$reason")
        }

        override fun onClosed(reason: Int) {
          val failureNow = System.currentTimeMillis()
          sessionActive = false
          activePeerCount = 0
          lastCloseReason = reason
          closeFailureCount.incrementAndGet()
          closesSinceRealResult++
          state = "CLOSED"
          detail = "API36 RangingManager session closed reason=$reason; independent BLE evidence remains active"
          session = null
          fingerprint = ""
          peerByUuid.clear()
          registerFailure(failureNow, "closed reason=$reason")
          if (!hasFreshResult(failureNow) && closesSinceRealResult >= BleAcquisitionPolicy.SYSTEM_RANGING_CLOSES_BEFORE_YIELD) {
            activateBleYield(failureNow, "${closesSinceRealResult} closes without a real platform distance")
          }
        }

        override fun onStarted(peer: RangingDevice, technology: Int) {
          sessionActive = true
          state = "ACTIVE_NO_RESULT"
          val id = peerByUuid[peer.uuid] ?: peer.uuid.toString()
          detail = "API36 ranging started peer=$id technology=${technologyName(technology)}"
        }

        override fun onStopped(peer: RangingDevice, technology: Int) {
          val id = peerByUuid[peer.uuid] ?: peer.uuid.toString()
          detail = "API36 ranging stopped peer=$id technology=${technologyName(technology)}; independent BLE evidence remains available"
        }

        override fun onResults(peer: RangingDevice, data: RangingData) {
          val peerNodeId = peerByUuid[peer.uuid] ?: return
          val distance = data.distance
          val confidence = distance?.confidence ?: RangingMeasurement.CONFIDENCE_LOW
          val distanceM = distance?.measurement?.takeIf { it.isFinite() && it >= 0.0 }
          val sigma = distanceM?.let {
            when (confidence) {
              RangingMeasurement.CONFIDENCE_HIGH -> maxOf(0.75, it * 0.30)
              RangingMeasurement.CONFIDENCE_MEDIUM -> maxOf(1.25, it * 0.50)
              else -> maxOf(1.75, it * 0.75)
            }
          }
          val quality = when (confidence) {
            RangingMeasurement.CONFIDENCE_HIGH -> "HIGH"
            RangingMeasurement.CONFIDENCE_MEDIUM -> "MEDIUM"
            else -> "LOW"
          }
          val technology = technologyName(data.rangingTechnology)
          val rssi = if (data.hasRssi()) data.rssi.toDouble() else null
          val received = System.currentTimeMillis()
          measurements[peerNodeId] = Measurement(
            peerNodeId = peerNodeId,
            monotonicNs = data.timestampMillis * 1_000_000L,
            distanceM = distanceM,
            distanceSigmaM = sigma,
            rssiDbm = rssi,
            quality = quality,
            technology = technology,
            sourceDetail = "Android API36 RangingManager raw session; technology=$technology; platform confidence=$confidence; conservative sigma derived from platform confidence",
            receivedWallMs = received,
          )
          lastResultWallMs = received
          resultCount.incrementAndGet()
          if (distanceM != null) registerRealRangeSuccess()
          state = if (distanceM != null) "ACTIVE_RESULT" else "ACTIVE_NO_DISTANCE"
          detail = "API36 RangingManager live result peer=$peerNodeId technology=$technology distance=${distanceM ?: "null"}"
        }
      }

      val newSession = manager.createRangingSession(context.mainExecutor, callback)
      if (newSession == null) {
        state = "CREATE_FAILED"
        detail = "API36 RangingManager could not create a session; independent BLE evidence remains active"
        registerFailure(now, "create failed")
        return
      }
      session = newSession
      fingerprint = nextFingerprint
      state = "STARTING"
      detail = "API36 RangingManager session starting for ${normalized.size} peer(s)"
      newSession.start(preference)
    } catch (e: SecurityException) {
      lastError = "${e.javaClass.simpleName}: ${e.message}"
      state = "PERMISSION_REQUIRED"
      detail = "API36 RangingManager permission denied: ${e.message}; independent BLE evidence remains active"
      closeSessionOnly()
      registerFailure(now, "permission")
    } catch (e: Throwable) {
      unexpectedFailureCount.incrementAndGet()
      lastError = "${e.javaClass.simpleName}: ${e.message}"
      state = "FAILED"
      detail = "API36 RangingManager unavailable for current peers: ${e.javaClass.simpleName}: ${e.message}; independent BLE evidence remains active"
      closeSessionOnly()
      registerFailure(now, e.javaClass.simpleName)
    }
  }

  @SuppressLint("MissingPermission")
  private fun closeSessionOnly() {
    val existing = session
    session = null
    try { existing?.stop() } catch (_: Throwable) {}
    try { existing?.close() } catch (_: Throwable) {}
    sessionActive = false
    activePeerCount = 0
    fingerprint = ""
    peerByUuid.clear()
  }

  private fun technologyName(value: Int): String = when (value) {
    RangingManager.UWB -> "ANDROID_RANGING_UWB"
    RangingManager.BLE_CS -> "ANDROID_RANGING_BLE_CS"
    RangingManager.WIFI_NAN_RTT -> "ANDROID_RANGING_WIFI_NAN_RTT"
    RangingManager.BLE_RSSI -> "ANDROID_RANGING_BLE_RSSI"
    else -> "UNKNOWN"
  }
}
