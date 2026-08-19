package com.trochez.bodyfindernative

import android.annotation.SuppressLint
import android.content.Context
import android.os.Build
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
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap

/**
 * Android 16 / API-36 raw BLE-RSSI adapter for Body Finder peers.
 *
 * Peer discovery remains Body Finder's manufacturer-data BLE advertisement.
 * The system Ranging API is used only after the advertisement identity has been
 * bound to the currently observed Bluetooth address. If the session cannot be
 * opened or stops producing data, callers keep the conservative manual scan
 * RSSI fallback. No UWB/BT-CS/NAN-RTT result is claimed by this class.
 */
@RequiresApi(36)
internal object SystemRangingApi36 {
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

  private var session: RangingSession? = null
  private var fingerprint: String = ""
  private val peerByUuid = ConcurrentHashMap<UUID, String>()
  val measurements = ConcurrentHashMap<String, Measurement>()

  @SuppressLint("MissingPermission")
  fun stop() {
    try { session?.stop() } catch (_: Throwable) {}
    try { session?.close() } catch (_: Throwable) {}
    session = null
    sessionActive = false
    fingerprint = ""
    peerByUuid.clear()
    measurements.clear()
  }

  @SuppressLint("MissingPermission")
  fun refresh(context: Context, peers: List<Peer>) {
    val normalized = peers
      .filter { it.nodeId.isNotBlank() && it.bluetoothAddress.matches(Regex("([0-9A-F]{2}:){5}[0-9A-F]{2}")) }
      .distinctBy { it.nodeId }
      .sortedBy { it.nodeId }
    val nextFingerprint = normalized.joinToString("|") { "${it.nodeId}@${it.bluetoothAddress}" }
    if (nextFingerprint == fingerprint && session != null) return

    stop()
    if (normalized.isEmpty()) {
      detail = "API36 RangingManager ready; awaiting a Body Finder BLE peer/address binding"
      return
    }

    try {
      val manager = context.getSystemService(RangingManager::class.java)
      if (manager == null) {
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
          detail = "API36 RangingManager raw BLE-RSSI session opened for ${normalized.size} peer(s)"
        }

        override fun onOpenFailed(reason: Int) {
          sessionActive = false
          detail = "API36 RangingManager session open failed reason=$reason; BLE scan RSSI fallback remains active"
        }

        override fun onClosed(reason: Int) {
          sessionActive = false
          detail = "API36 RangingManager session closed reason=$reason; BLE scan RSSI fallback remains active"
        }

        override fun onStarted(peer: RangingDevice, technology: Int) {
          sessionActive = true
          val id = peerByUuid[peer.uuid] ?: peer.uuid.toString()
          detail = "API36 ranging started peer=$id technology=${technologyName(technology)}"
        }

        override fun onStopped(peer: RangingDevice, technology: Int) {
          val id = peerByUuid[peer.uuid] ?: peer.uuid.toString()
          detail = "API36 ranging stopped peer=$id technology=${technologyName(technology)}; fallback remains available"
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
          measurements[peerNodeId] = Measurement(
            peerNodeId = peerNodeId,
            monotonicNs = data.timestampMillis * 1_000_000L,
            distanceM = distanceM,
            distanceSigmaM = sigma,
            rssiDbm = rssi,
            quality = quality,
            technology = technology,
            sourceDetail = "Android API36 RangingManager raw session; technology=$technology; platform confidence=$confidence; conservative sigma derived from confidence because API36 base does not guarantee distance standard deviation",
            receivedWallMs = System.currentTimeMillis(),
          )
          detail = "API36 RangingManager live result peer=$peerNodeId technology=$technology"
        }
      }

      val newSession = manager.createRangingSession(context.mainExecutor, callback)
      if (newSession == null) {
        detail = "API36 RangingManager could not create a session; BLE scan RSSI fallback remains active"
        return
      }
      session = newSession
      fingerprint = nextFingerprint
      detail = "API36 RangingManager session starting for ${normalized.size} peer(s)"
      newSession.start(preference)
    } catch (e: SecurityException) {
      detail = "API36 RangingManager permission denied: ${e.message}; BLE scan RSSI fallback remains active"
      stopSessionOnly()
    } catch (e: Throwable) {
      detail = "API36 RangingManager unavailable for current peers: ${e.javaClass.simpleName}: ${e.message}; BLE scan RSSI fallback remains active"
      stopSessionOnly()
    }
  }

  @SuppressLint("MissingPermission")
  private fun stopSessionOnly() {
    try { session?.stop() } catch (_: Throwable) {}
    try { session?.close() } catch (_: Throwable) {}
    session = null
    sessionActive = false
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
