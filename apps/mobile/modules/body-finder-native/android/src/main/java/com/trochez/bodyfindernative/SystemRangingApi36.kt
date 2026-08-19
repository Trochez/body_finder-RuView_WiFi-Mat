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

/**
 * Android API-36+ raw BLE-RSSI adapter for Body Finder peers.
 *
 * This is a preferred source only when it produces a fresh real distance.
 * BodyFinderNativeModule keeps its scan-RSSI fallback completely independent:
 * session close/open failure here must never clear fallback RSSI windows.
 */
@RequiresApi(36)
internal object SystemRangingApi36 {
  private const val RESULT_FRESHNESS_MS = 5_000L
  private const val RETRY_BACKOFF_MS = 2_000L

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

  private var session: RangingSession? = null
  private var fingerprint: String = ""
  private val peerByUuid = ConcurrentHashMap<UUID, String>()
  private val resultCount = AtomicLong(0)
  val measurements = ConcurrentHashMap<String, Measurement>()

  fun hasFreshResult(now: Long = System.currentTimeMillis()): Boolean =
    measurements.values.any { it.distanceM != null && now - it.receivedWallMs <= RESULT_FRESHNESS_MS }

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
    put("retry_in_ms", max(0L, nextRetryWallMs - now))
    put("fresh_result_available", hasFreshResult(now))
  }

  @SuppressLint("MissingPermission")
  fun stop() {
    closeSessionOnly()
    measurements.clear()
    resultCount.set(0)
    requestedPeerCount = 0
    activePeerCount = 0
    lastResultWallMs = null
    lastCloseReason = null
    lastOpenFailureReason = null
    lastError = null
    nextRetryWallMs = 0
    state = "IDLE"
    detail = "API36 RangingManager idle"
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
    if (nextFingerprint == fingerprint && session != null) return
    if (now < nextRetryWallMs) {
      state = "BACKOFF"
      detail = "API36 RangingManager retry backoff active; BLE scan RSSI fallback remains available"
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
          lastError = null
          detail = "API36 RangingManager raw BLE-RSSI session opened for ${normalized.size} peer(s)"
        }

        override fun onOpenFailed(reason: Int) {
          sessionActive = false
          activePeerCount = 0
          lastOpenFailureReason = reason
          state = "OPEN_FAILED"
          detail = "API36 RangingManager session open failed reason=$reason; independent BLE scan RSSI fallback remains active"
          session = null
          fingerprint = ""
          peerByUuid.clear()
          nextRetryWallMs = System.currentTimeMillis() + RETRY_BACKOFF_MS
        }

        override fun onClosed(reason: Int) {
          sessionActive = false
          activePeerCount = 0
          lastCloseReason = reason
          state = "CLOSED"
          detail = "API36 RangingManager session closed reason=$reason; independent BLE scan RSSI fallback remains active and system ranging will retry"
          session = null
          fingerprint = ""
          peerByUuid.clear()
          nextRetryWallMs = System.currentTimeMillis() + RETRY_BACKOFF_MS
        }

        override fun onStarted(peer: RangingDevice, technology: Int) {
          sessionActive = true
          state = "ACTIVE_NO_RESULT"
          val id = peerByUuid[peer.uuid] ?: peer.uuid.toString()
          detail = "API36 ranging started peer=$id technology=${technologyName(technology)}"
        }

        override fun onStopped(peer: RangingDevice, technology: Int) {
          val id = peerByUuid[peer.uuid] ?: peer.uuid.toString()
          detail = "API36 ranging stopped peer=$id technology=${technologyName(technology)}; independent BLE RSSI fallback remains available"
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
            sourceDetail = "Android API36 RangingManager raw session; technology=$technology; platform confidence=$confidence; conservative sigma derived from confidence because API36 base does not guarantee distance standard deviation",
            receivedWallMs = received,
          )
          lastResultWallMs = received
          resultCount.incrementAndGet()
          state = if (distanceM != null) "ACTIVE_RESULT" else "ACTIVE_NO_DISTANCE"
          detail = "API36 RangingManager live result peer=$peerNodeId technology=$technology distance=${distanceM ?: "null"}"
        }
      }

      val newSession = manager.createRangingSession(context.mainExecutor, callback)
      if (newSession == null) {
        state = "CREATE_FAILED"
        detail = "API36 RangingManager could not create a session; BLE scan RSSI fallback remains active"
        nextRetryWallMs = now + RETRY_BACKOFF_MS
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
      detail = "API36 RangingManager permission denied: ${e.message}; BLE scan RSSI fallback remains active"
      closeSessionOnly()
      nextRetryWallMs = now + RETRY_BACKOFF_MS
    } catch (e: Throwable) {
      lastError = "${e.javaClass.simpleName}: ${e.message}"
      state = "FAILED"
      detail = "API36 RangingManager unavailable for current peers: ${e.javaClass.simpleName}: ${e.message}; BLE scan RSSI fallback remains active"
      closeSessionOnly()
      nextRetryWallMs = now + RETRY_BACKOFF_MS
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
