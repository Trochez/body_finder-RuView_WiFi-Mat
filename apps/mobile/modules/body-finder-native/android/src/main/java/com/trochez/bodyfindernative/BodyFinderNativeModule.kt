package com.trochez.bodyfindernative

import android.Manifest
import android.bluetooth.BluetoothManager
import android.bluetooth.le.AdvertiseCallback
import android.bluetooth.le.AdvertiseData
import android.bluetooth.le.AdvertiseSettings
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.content.pm.PackageManager
import android.location.LocationManager
import android.net.wifi.WifiManager
import android.os.Build
import android.os.SystemClock
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import org.json.JSONArray
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.MulticastSocket
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.ConcurrentLinkedDeque
import java.util.concurrent.atomic.AtomicLong
import kotlin.concurrent.thread
import kotlin.math.max
import kotlin.math.pow

private const val PORT = 47777
private const val GROUP = "239.255.77.77"
private const val PROTOCOL = 2
private const val MANUFACTURER_ID = 0x05F1
private const val RANGE_PERMISSION = "android.permission.RANGING"
private const val PEER_EXPIRY_MS = 5_000L
private const val RANGE_FRESHNESS_MS = 5_000L
private const val WINDOW_RETENTION_MS = 8_000L
private const val MIN_SAMPLES_FOR_RANGE = 3
private const val MAX_RSSI_SAMPLES = 21

private data class RssiSample(val rssi: Int, val txPower: Int, val ms: Long)

private object FabricRuntime {
  @Volatile var running = false
  @Volatile var nodeId = UUID.randomUUID().toString()
  @Volatile var displayName = Build.MODEL ?: "Android"
  @Volatile var sessionId = "body-finder-lab"
  @Volatile var baseline: Double? = null
  @Volatile var sigma: Double? = null
  @Volatile var scanning = false
  @Volatile var bleScanning = false
  @Volatile var bleAdvertising = false
  @Volatile var bleDetail = "BLE not started"
  @Volatile var bleScanState = "IDLE"
  @Volatile var bleAdvertiseState = "IDLE"
  @Volatile var bleScanMode = "NONE"
  @Volatile var bleScanFailureCode: Int? = null
  @Volatile var bleAdvertiseFailureCode: Int? = null
  @Volatile var bleAdvertiseStartedWallMs: Long? = null
  @Volatile var socketState = "IDLE"
  @Volatile var multicastJoinState = "IDLE"
  @Volatile var publishedGeometryJson: String? = null

  var socket: MulticastSocket? = null
  var advertiser: android.bluetooth.le.BluetoothLeAdvertiser? = null
  var scanner: android.bluetooth.le.BluetoothLeScanner? = null
  var advertiseCallback: AdvertiseCallback? = null
  var scanCallback: ScanCallback? = null

  val peers = ConcurrentHashMap<String, Pair<String, Long>>()
  val peerPacketCounts = ConcurrentHashMap<String, AtomicLong>()
  val peerLastSeenWallMs = ConcurrentHashMap<String, Long>()
  val rssiWindows = ConcurrentHashMap<String, ConcurrentLinkedDeque<RssiSample>>()
  val bleAddressByIdentity = ConcurrentHashMap<String, String>()
  val bleLastSeenWallMsByIdentity = ConcurrentHashMap<String, Long>()
  val bleSeenCountByIdentity = ConcurrentHashMap<String, AtomicLong>()
  val addressRebindCountByIdentity = ConcurrentHashMap<String, AtomicLong>()

  val totalScanResults = AtomicLong(0)
  val bodyFinderScanResults = AtomicLong(0)
  val malformedBodyFinderPayloads = AtomicLong(0)
  val selfScanResultsIgnored = AtomicLong(0)
  val advertiseRestartCount = AtomicLong(0)
  val txPackets = AtomicLong(0)
  val rxPackets = AtomicLong(0)
  val rxProtocolV2Packets = AtomicLong(0)
  val rxSameSessionPackets = AtomicLong(0)
  val peerExpireCount = AtomicLong(0)
  @Volatile var lastAnyScanResultWallMs: Long? = null
  @Volatile var lastBodyFinderScanResultWallMs: Long? = null

  fun resetDiagnostics() {
    bleDetail = "BLE not started"
    bleScanState = "IDLE"
    bleAdvertiseState = "IDLE"
    bleScanMode = "NONE"
    bleScanFailureCode = null
    bleAdvertiseFailureCode = null
    bleAdvertiseStartedWallMs = null
    socketState = "IDLE"
    multicastJoinState = "IDLE"
    totalScanResults.set(0)
    bodyFinderScanResults.set(0)
    malformedBodyFinderPayloads.set(0)
    selfScanResultsIgnored.set(0)
    advertiseRestartCount.set(0)
    txPackets.set(0)
    rxPackets.set(0)
    rxProtocolV2Packets.set(0)
    rxSameSessionPackets.set(0)
    peerExpireCount.set(0)
    lastAnyScanResultWallMs = null
    lastBodyFinderScanResultWallMs = null
    peerPacketCounts.clear()
    peerLastSeenWallMs.clear()
    bleLastSeenWallMsByIdentity.clear()
    bleSeenCountByIdentity.clear()
    addressRebindCountByIdentity.clear()
  }

  fun stopBle() {
    try { advertiseCallback?.let { advertiser?.stopAdvertising(it) } } catch (_: Throwable) {}
    try { scanCallback?.let { scanner?.stopScan(it) } } catch (_: Throwable) {}
    if (Build.VERSION.SDK_INT >= 36) {
      try { SystemRangingApi36.stop() } catch (_: Throwable) {}
    }
    advertiser = null
    scanner = null
    advertiseCallback = null
    scanCallback = null
    bleScanning = false
    bleAdvertising = false
    bleScanState = "IDLE"
    bleAdvertiseState = "IDLE"
    rssiWindows.clear()
    bleAddressByIdentity.clear()
  }

  fun stop() {
    running = false
    try { socket?.close() } catch (_: Throwable) {}
    socket = null
    socketState = "CLOSED"
    peers.clear()
    publishedGeometryJson = null
    stopBle()
  }
}

class BodyFinderNativeModule : Module() {
  override fun definition() = ModuleDefinition {
    Name("BodyFinderNative")

    Function("getCapabilitiesJson") {
      val ctx = appContext.reactContext ?: return@Function "{}"
      deviceReport(ctx).toString()
    }
    Function("getDiagnosticsJson") {
      val ctx = appContext.reactContext ?: return@Function "{}"
      diagnostics(ctx).toString()
    }
    Function("getWifiRssi") {
      val ctx = appContext.reactContext ?: return@Function null
      wifiRssi(ctx)
    }
    Function("updateLocalState") { baseline: Double?, sigma: Double?, scanning: Boolean ->
      FabricRuntime.baseline = baseline
      FabricRuntime.sigma = sigma
      FabricRuntime.scanning = scanning
      true
    }
    Function("updatePublishedGeometry") { publish: Boolean, geometryJson: String? ->
      FabricRuntime.publishedGeometryJson = if (publish && !geometryJson.isNullOrBlank()) {
        try { JSONObject(geometryJson).toString() } catch (_: Throwable) { null }
      } else null
      true
    }
    AsyncFunction("startFabric") { nodeId: String?, displayName: String?, sessionId: String? ->
      val ctx = appContext.reactContext ?: return@AsyncFunction false
      FabricRuntime.stop()
      FabricRuntime.resetDiagnostics()
      val prefs = ctx.getSharedPreferences("body-finder-runtime", Context.MODE_PRIVATE)
      val saved = prefs.getString("node-id-v2", null)
      val chosen = nodeId?.takeIf { it.isNotBlank() }
        ?: saved
        ?: UUID.randomUUID().toString().also {
          prefs.edit().putString("node-id-v2", it).apply()
        }
      FabricRuntime.nodeId = chosen
      FabricRuntime.displayName = displayName?.takeIf { it.isNotBlank() } ?: (Build.MODEL ?: "Android")
      FabricRuntime.sessionId = sessionId?.takeIf { it.isNotBlank() } ?: "body-finder-lab"
      FabricRuntime.running = true
      startBle(ctx.applicationContext)
      startNetworkThread(ctx.applicationContext)
      true
    }
    Function("stopFabric") {
      FabricRuntime.stop()
      true
    }
    Function("getPeersJson") {
      expirePeers(System.currentTimeMillis())
      val arr = JSONArray()
      FabricRuntime.peers.values.forEach { pair ->
        try { arr.put(JSONObject(pair.first)) } catch (_: Throwable) {}
      }
      arr.toString()
    }
    Function("getLocalAdvertisementJson") {
      val ctx = appContext.reactContext ?: return@Function "{}"
      advertisement(ctx).toString()
    }
  }

  private fun probe(state: String, detail: String) = JSONObject().put("state", state).put("detail", detail)
  private fun hasPermission(ctx: Context, permission: String) =
    Build.VERSION.SDK_INT < 23 || ctx.checkSelfPermission(permission) == PackageManager.PERMISSION_GRANTED
  private fun state(ok: Boolean, detail: String) = probe(if (ok) "WORKING" else "UNSUPPORTED", detail)
  private fun ageMs(now: Long, then: Long?): Any = if (then == null) JSONObject.NULL else max(0L, now - then)

  private fun legacyBluetoothPermissionsGranted(ctx: Context): Boolean {
    if (Build.VERSION.SDK_INT >= 31) return true
    return hasPermission(ctx, Manifest.permission.BLUETOOTH) &&
      hasPermission(ctx, Manifest.permission.BLUETOOTH_ADMIN) &&
      hasPermission(ctx, Manifest.permission.ACCESS_FINE_LOCATION)
  }

  private fun modernBluetoothPermissionsGranted(ctx: Context): Boolean {
    if (Build.VERSION.SDK_INT < 31) return true
    return hasPermission(ctx, Manifest.permission.BLUETOOTH_SCAN) &&
      hasPermission(ctx, Manifest.permission.BLUETOOTH_ADVERTISE) &&
      hasPermission(ctx, Manifest.permission.BLUETOOTH_CONNECT)
  }

  private fun bluetoothPermissionsGranted(ctx: Context) =
    legacyBluetoothPermissionsGranted(ctx) && modernBluetoothPermissionsGranted(ctx)

  private fun locationServiceEnabled(ctx: Context): Boolean? {
    if (Build.VERSION.SDK_INT >= 31) return null
    return try {
      val manager = ctx.getSystemService(Context.LOCATION_SERVICE) as? LocationManager ?: return false
      if (Build.VERSION.SDK_INT >= 28) manager.isLocationEnabled else true
    } catch (_: Throwable) { null }
  }

  private fun deviceReport(ctx: Context) = JSONObject().apply {
    put("platform", "android")
    put("manufacturer", Build.MANUFACTURER ?: "unknown")
    put("model", Build.MODEL ?: "unknown")
    put("android_api", Build.VERSION.SDK_INT)
    put("capabilities", capabilityMap(ctx))
  }

  private fun freshFallbackReadyCount(now: Long = System.currentTimeMillis()): Int {
    return FabricRuntime.peers.values.count { pair ->
      try {
        val peer = JSONObject(pair.first)
        val identity = peer.optString("ble_identity").takeIf { it.isNotBlank() && it != "null" } ?: return@count false
        val samples = FabricRuntime.rssiWindows[identity]?.count { now - it.ms <= RANGE_FRESHNESS_MS } ?: 0
        samples >= MIN_SAMPLES_FOR_RANGE
      } catch (_: Throwable) { false }
    }
  }

  private fun capabilityMap(ctx: Context): JSONObject {
    val pm = ctx.packageManager
    val wifi = ctx.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
    val bleFeature = pm.hasSystemFeature(PackageManager.FEATURE_BLUETOOTH_LE)
    val blePerm = bluetoothPermissionsGranted(ctx)
    val liveFallbackCount = freshFallbackReadyCount()
    val bodyFinderSeen = FabricRuntime.bodyFinderScanResults.get() > 0
    return JSONObject().apply {
      put("wifi", state(wifi != null && wifi.isWifiEnabled, "Wi-Fi manager enabled"))
      put("wifi_rssi", state(wifiRssi(ctx) != null, "live connected-link RSSI; human-presence evidence only, never inter-node distance"))
      put("wifi_rtt", if (Build.VERSION.SDK_INT >= 28 && pm.hasSystemFeature(PackageManager.FEATURE_WIFI_RTT)) {
        probe("SUPPORTED_UNVERIFIED", "Wi-Fi RTT feature present; peer/AP ranging is not claimed until a live session reports measurements")
      } else state(false, "Wi-Fi RTT feature absent"))
      put("android_ranging_api", androidRangingProbe(ctx))
      put("ble", when {
        !bleFeature -> state(false, "BLE feature absent")
        !blePerm -> probe("PERMISSION_REQUIRED", "Bluetooth permissions required for this Android API level")
        Build.VERSION.SDK_INT < 31 && locationServiceEnabled(ctx) == false -> probe("PERMISSION_REQUIRED", "Location service must be enabled for reliable BLE scan on Android <= 11")
        else -> probe("WORKING", "BLE hardware and permissions available")
      })
      put("ble_peer_ranging", when {
        !bleFeature -> probe("UNSUPPORTED", "BLE feature absent")
        !blePerm -> probe("PERMISSION_REQUIRED", "Bluetooth permissions required")
        liveFallbackCount > 0 -> probe("WORKING_DEGRADED", "LIVE_BLE_RSSI: $liveFallbackCount peer range(s) ready from fresh Body Finder advertisement RSSI; conservative path-loss model with large sigma")
        Build.VERSION.SDK_INT >= 36 && SystemRangingApi36.hasFreshResult() -> probe("WORKING_DEGRADED", SystemRangingApi36.detail + "; fresh Android system ranging result available")
        bodyFinderSeen -> probe("WORKING_DEGRADED", "ACQUIRING: Body Finder BLE advertisement seen; waiting for enough fresh per-peer RSSI samples")
        FabricRuntime.bleScanning -> probe("SUPPORTED_UNVERIFIED", "ACQUIRING: BLE scan active but no Body Finder peer advertisement has been recognized yet")
        else -> probe("SUPPORTED_UNVERIFIED", FabricRuntime.bleDetail)
      })
      put("imu", state(pm.hasSystemFeature(PackageManager.FEATURE_SENSOR_ACCELEROMETER), "accelerometer feature"))
      put("automatic_geometry_compute", probe("WORKING", "protocol-v2 automatic geometry solver runs in the app"))
      put("geometry_publication", probe("WORKING", "elected coordinator attaches its derived GeometrySolution revision to protocol-v2 advertisements"))
      put("csi", probe("UNSUPPORTED", "No public/verified CSI adapter loaded; RSSI is never labeled CSI"))
      put("udp_fabric", probe(if (FabricRuntime.socketState == "BOUND") "WORKING_DEGRADED" else "SUPPORTED_UNVERIFIED", "local UDP multicast/broadcast; socket=${FabricRuntime.socketState}; multicast=${FabricRuntime.multicastJoinState}"))
      put("compute", probe("WORKING", "Android Body Finder application runtime"))
    }
  }

  private fun androidRangingProbe(ctx: Context): JSONObject {
    if (Build.VERSION.SDK_INT < 36) return probe("UNSUPPORTED", "android.ranging.RangingManager requires Android API 36+")
    if (!hasPermission(ctx, RANGE_PERMISSION)) return probe("PERMISSION_REQUIRED", "android.permission.RANGING is required")
    return try {
      val clazz = Class.forName("android.ranging.RangingManager")
      val method = Context::class.java.getMethod("getSystemService", Class::class.java)
      val service = method.invoke(ctx, clazz)
      when {
        service == null -> probe("UNSUPPORTED", "RangingManager service unavailable")
        SystemRangingApi36.hasFreshResult() -> probe("WORKING_DEGRADED", SystemRangingApi36.detail + "; live system ranging result observed")
        else -> probe("SUPPORTED_UNVERIFIED", SystemRangingApi36.detail + "; BLE RSSI fallback remains independent and available when scan samples are fresh")
      }
    } catch (e: Throwable) {
      probe("PROBE_FAILED", "RangingManager probe failed: ${e.javaClass.simpleName}")
    }
  }

  @Suppress("DEPRECATION")
  private fun wifiRssi(ctx: Context): Double? = try {
    val wm = ctx.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
    if (!wm.isWifiEnabled) null
    else wm.connectionInfo?.rssi?.toDouble()?.takeIf { it in -126.0..0.0 }
  } catch (_: Throwable) { null }

  private fun bleIdentity(nodeId: String = FabricRuntime.nodeId): String {
    val bytes = MessageDigest.getInstance("SHA-256")
      .digest(nodeId.toByteArray(Charsets.UTF_8))
      .copyOfRange(0, 8)
    return bytes.joinToString("") { "%02x".format(it.toInt() and 0xff) }
  }

  private fun addressFingerprint(address: String): String {
    val bytes = MessageDigest.getInstance("SHA-256")
      .digest((FabricRuntime.sessionId + ":" + address.uppercase()).toByteArray(Charsets.UTF_8))
      .copyOfRange(0, 6)
    return "sha256:" + bytes.joinToString("") { "%02x".format(it.toInt() and 0xff) }
  }

  private fun blePayload(): ByteArray {
    val id = bleIdentity()
    val out = ByteArray(10)
    out[0] = 0x42
    out[1] = 0x46
    for (i in 0 until 8) out[i + 2] = id.substring(i * 2, i * 2 + 2).toInt(16).toByte()
    return out
  }

  private fun payloadIdentity(data: ByteArray?): String? {
    if (data == null || data.size < 10 || data[0] != 0x42.toByte() || data[1] != 0x46.toByte()) return null
    return data.copyOfRange(2, 10).joinToString("") { "%02x".format(it.toInt() and 0xff) }
  }

  private fun startBle(ctx: Context) {
    try {
      val manager = ctx.getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager ?: run {
        FabricRuntime.bleDetail = "BluetoothManager unavailable"
        FabricRuntime.bleScanState = "UNAVAILABLE"
        return
      }
      val adapter = manager.adapter ?: run {
        FabricRuntime.bleDetail = "Bluetooth adapter unavailable"
        FabricRuntime.bleScanState = "UNAVAILABLE"
        return
      }
      if (!adapter.isEnabled) {
        FabricRuntime.bleDetail = "Bluetooth disabled"
        FabricRuntime.bleScanState = "DISABLED"
        return
      }
      if (!bluetoothPermissionsGranted(ctx)) {
        FabricRuntime.bleDetail = "Bluetooth permission required for API ${Build.VERSION.SDK_INT}"
        FabricRuntime.bleScanState = "PERMISSION_REQUIRED"
        return
      }
      if (Build.VERSION.SDK_INT < 31 && locationServiceEnabled(ctx) == false) {
        FabricRuntime.bleDetail = "Location service disabled; Android <=11 may suppress BLE scan results"
        FabricRuntime.bleScanState = "LOCATION_REQUIRED"
        return
      }
      val scanner = adapter.bluetoothLeScanner ?: run {
        FabricRuntime.bleDetail = "BLE scanner unavailable"
        FabricRuntime.bleScanState = "UNAVAILABLE"
        return
      }
      val advertiser = adapter.bluetoothLeAdvertiser
      FabricRuntime.scanner = scanner
      FabricRuntime.advertiser = advertiser
      FabricRuntime.bleScanState = "STARTING"

      val scanCb = object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult) { recordScan(result) }
        override fun onBatchScanResults(results: MutableList<ScanResult>) { results.forEach { recordScan(it) } }
        override fun onScanFailed(errorCode: Int) {
          FabricRuntime.bleScanning = false
          FabricRuntime.bleScanState = "FAILED"
          FabricRuntime.bleScanFailureCode = errorCode
          FabricRuntime.bleDetail = "BLE scan failed code=$errorCode"
        }
      }
      FabricRuntime.scanCallback = scanCb
      val settings = ScanSettings.Builder()
        .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
        .setReportDelay(0L)
        .setCallbackType(ScanSettings.CALLBACK_TYPE_ALL_MATCHES)
        .build()
      val prefix = byteArrayOf(0x42, 0x46)
      val mask = byteArrayOf(0xff.toByte(), 0xff.toByte())
      val filter = ScanFilter.Builder()
        .setManufacturerData(MANUFACTURER_ID, prefix, mask)
        .build()
      try {
        scanner.startScan(listOf(filter), settings, scanCb)
        FabricRuntime.bleScanMode = "LOW_LATENCY_FILTERED"
      } catch (filteredError: Throwable) {
        scanner.startScan(null, settings, scanCb)
        FabricRuntime.bleScanMode = "LOW_LATENCY_UNFILTERED_FALLBACK"
        FabricRuntime.bleDetail = "Filtered BLE scan unavailable (${filteredError.javaClass.simpleName}); unfiltered fallback active"
      }
      FabricRuntime.bleScanning = true
      FabricRuntime.bleScanState = "ACTIVE_NO_BODY_FINDER_PEER"

      if (advertiser != null) {
        FabricRuntime.bleAdvertiseState = "STARTING"
        val advCb = object : AdvertiseCallback() {
          override fun onStartSuccess(settingsInEffect: AdvertiseSettings) {
            FabricRuntime.bleAdvertising = true
            FabricRuntime.bleAdvertiseState = "ACTIVE"
            FabricRuntime.bleAdvertiseStartedWallMs = System.currentTimeMillis()
            FabricRuntime.bleDetail = "BLE scan + Body Finder advertisement active"
          }
          override fun onStartFailure(errorCode: Int) {
            FabricRuntime.bleAdvertising = false
            FabricRuntime.bleAdvertiseState = "FAILED"
            FabricRuntime.bleAdvertiseFailureCode = errorCode
            FabricRuntime.bleDetail = "BLE scan active; advertisement unavailable code=$errorCode"
          }
        }
        FabricRuntime.advertiseCallback = advCb
        val advertiseSettings = AdvertiseSettings.Builder()
          .setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_LATENCY)
          .setTxPowerLevel(AdvertiseSettings.ADVERTISE_TX_POWER_MEDIUM)
          .setConnectable(false)
          .build()
        val data = AdvertiseData.Builder()
          .addManufacturerData(MANUFACTURER_ID, blePayload())
          .setIncludeTxPowerLevel(true)
          .build()
        FabricRuntime.advertiseRestartCount.incrementAndGet()
        advertiser.startAdvertising(advertiseSettings, data, advCb)
      } else {
        FabricRuntime.bleAdvertiseState = "UNSUPPORTED"
        FabricRuntime.bleDetail = "BLE scan active; peripheral advertising unsupported on this device"
      }
    } catch (e: SecurityException) {
      FabricRuntime.bleScanState = "PERMISSION_REQUIRED"
      FabricRuntime.bleDetail = "BLE permission denied: ${e.message}"
    } catch (e: Throwable) {
      FabricRuntime.bleScanState = "FAILED"
      FabricRuntime.bleDetail = "BLE start failed: ${e.javaClass.simpleName}: ${e.message}"
    }
  }

  private fun recordScan(result: ScanResult) {
    val now = System.currentTimeMillis()
    FabricRuntime.totalScanResults.incrementAndGet()
    FabricRuntime.lastAnyScanResultWallMs = now
    val raw = result.scanRecord?.getManufacturerSpecificData(MANUFACTURER_ID) ?: return
    val id = payloadIdentity(raw)
    if (id == null) {
      FabricRuntime.malformedBodyFinderPayloads.incrementAndGet()
      return
    }
    if (id == bleIdentity()) {
      FabricRuntime.selfScanResultsIgnored.incrementAndGet()
      return
    }
    FabricRuntime.bodyFinderScanResults.incrementAndGet()
    FabricRuntime.lastBodyFinderScanResultWallMs = now
    FabricRuntime.bleLastSeenWallMsByIdentity[id] = now
    FabricRuntime.bleSeenCountByIdentity.computeIfAbsent(id) { AtomicLong(0) }.incrementAndGet()
    FabricRuntime.bleScanState = "ACTIVE_PEER_SEEN"

    val tx = result.scanRecord?.txPowerLevel?.takeIf { it in -100..20 } ?: -59
    val queue = FabricRuntime.rssiWindows.computeIfAbsent(id) { ConcurrentLinkedDeque() }
    queue.addLast(RssiSample(result.rssi, tx, now))
    try {
      val address = result.device.address?.uppercase()
      if (!address.isNullOrBlank()) {
        val old = FabricRuntime.bleAddressByIdentity.put(id, address)
        if (old != null && old != address) {
          FabricRuntime.addressRebindCountByIdentity.computeIfAbsent(id) { AtomicLong(0) }.incrementAndGet()
        }
      }
    } catch (_: SecurityException) {}
    while (queue.size > MAX_RSSI_SAMPLES) queue.pollFirst()
    while (true) {
      val first = queue.peekFirst() ?: break
      if (now - first.ms <= WINDOW_RETENTION_MS) break else queue.pollFirst()
    }
  }

  private fun median(values: List<Double>): Double {
    val sorted = values.sorted()
    val n = sorted.size
    return if (n % 2 == 0) (sorted[n / 2 - 1] + sorted[n / 2]) / 2.0 else sorted[n / 2]
  }

  private fun desiredSystemRangingPeers(): List<SystemRangingApi36.Peer> {
    if (Build.VERSION.SDK_INT < 36) return emptyList()
    return FabricRuntime.peers.values.mapNotNull { pair ->
      try {
        val peer = JSONObject(pair.first)
        val peerId = peer.optString("node_id").takeIf { it.isNotBlank() } ?: return@mapNotNull null
        val identity = peer.optString("ble_identity").takeIf { it.isNotBlank() && it != "null" } ?: return@mapNotNull null
        val address = FabricRuntime.bleAddressByIdentity[identity] ?: return@mapNotNull null
        SystemRangingApi36.Peer(peerId, address)
      } catch (_: Throwable) { null }
    }
  }

  private fun fallbackObservation(peer: JSONObject, now: Long, mono: Long): JSONObject? {
    val peerId = peer.optString("node_id").takeIf { it.isNotBlank() } ?: return null
    val identity = peer.optString("ble_identity").takeIf { it.isNotBlank() && it != "null" } ?: return null
    val samples = FabricRuntime.rssiWindows[identity]?.filter { now - it.ms <= RANGE_FRESHNESS_MS } ?: emptyList()
    if (samples.size < MIN_SAMPLES_FOR_RANGE) return null
    val rssi = median(samples.map { it.rssi.toDouble() })
    val tx = median(samples.map { it.txPower.toDouble() })
    val pathLossN = 2.2
    val distance = 10.0.pow((tx - rssi) / (10.0 * pathLossN)).coerceIn(0.20, 30.0)
    if (!distance.isFinite() || distance <= 0.0) return null
    val sigma = max(1.5, distance * 0.75)
    return JSONObject()
      .put("session_id", FabricRuntime.sessionId)
      .put("observer_node_id", FabricRuntime.nodeId)
      .put("peer_node_id", peerId)
      .put("technology", "BLE_RSSI")
      .put("monotonic_ns", mono)
      .put("distance_m", distance)
      .put("distance_sigma_m", sigma)
      .put("azimuth_deg", JSONObject.NULL)
      .put("azimuth_sigma_deg", JSONObject.NULL)
      .put("elevation_deg", JSONObject.NULL)
      .put("elevation_sigma_deg", JSONObject.NULL)
      .put("rssi_dbm", rssi)
      .put("quality", "LOW")
      .put("source_detail", "Live Body Finder BLE advertisement RSSI fallback; median ${samples.size} fresh samples; Tx=$tx dBm; path-loss n=$pathLossN; intentionally large uncertainty; independent of Android system ranging; not UWB/RTT/CSI")
  }

  private fun rangeObservations(): JSONArray {
    val arr = JSONArray()
    val now = System.currentTimeMillis()
    val mono = SystemClock.elapsedRealtimeNanos()
    FabricRuntime.peers.values.forEach { pair ->
      try {
        val peer = JSONObject(pair.first)
        val peerId = peer.optString("node_id")
        if (Build.VERSION.SDK_INT >= 36) {
          val system = SystemRangingApi36.measurements[peerId]
          if (system != null && now - system.receivedWallMs <= RANGE_FRESHNESS_MS && system.distanceM != null) {
            arr.put(
              JSONObject()
                .put("session_id", FabricRuntime.sessionId)
                .put("observer_node_id", FabricRuntime.nodeId)
                .put("peer_node_id", peerId)
                .put("technology", system.technology)
                .put("monotonic_ns", system.monotonicNs)
                .put("distance_m", system.distanceM)
                .put("distance_sigma_m", system.distanceSigmaM ?: max(1.5, system.distanceM * 0.75))
                .put("azimuth_deg", JSONObject.NULL)
                .put("azimuth_sigma_deg", JSONObject.NULL)
                .put("elevation_deg", JSONObject.NULL)
                .put("elevation_sigma_deg", JSONObject.NULL)
                .put("rssi_dbm", system.rssiDbm ?: JSONObject.NULL)
                .put("quality", system.quality)
                .put("source_detail", system.sourceDetail)
            )
            return@forEach
          }
        }
        fallbackObservation(peer, now, mono)?.let { arr.put(it) }
      } catch (_: Throwable) {}
    }
    return arr
  }

  private fun peerBleDiagnostics(now: Long): JSONArray {
    val arr = JSONArray()
    FabricRuntime.peers.values.forEach { pair ->
      try {
        val peer = JSONObject(pair.first)
        val peerId = peer.optString("node_id")
        val identity = peer.optString("ble_identity").takeIf { it.isNotBlank() && it != "null" }
        val queue = identity?.let { FabricRuntime.rssiWindows[it] }
        val fresh = queue?.filter { now - it.ms <= RANGE_FRESHNESS_MS } ?: emptyList()
        val retained = queue?.filter { now - it.ms <= WINDOW_RETENTION_MS } ?: emptyList()
        val last = retained.maxByOrNull { it.ms }
        val seenAt = identity?.let { FabricRuntime.bleLastSeenWallMsByIdentity[it] }
        val address = identity?.let { FabricRuntime.bleAddressByIdentity[it] }
        val bindingState = when {
          identity == null -> "UDP_ONLY"
          seenAt == null -> "BLE_IDENTITY_KNOWN"
          fresh.isEmpty() -> "BLE_IDENTITY_SEEN"
          fresh.size < MIN_SAMPLES_FOR_RANGE -> "SAMPLES_ACQUIRING"
          else -> "RANGE_READY"
        }
        val blocker = when (bindingState) {
          "UDP_ONLY" -> "NO_BLE_IDENTITY"
          "BLE_IDENTITY_KNOWN" -> "ADVERTISEMENT_NOT_SEEN"
          "BLE_IDENTITY_SEEN" -> "STALE_SAMPLES"
          "SAMPLES_ACQUIRING" -> "INSUFFICIENT_SAMPLES"
          else -> null
        }
        arr.put(JSONObject().apply {
          put("node_id", peerId)
          put("ble_identity", identity ?: JSONObject.NULL)
          put("address_fingerprint", address?.let { addressFingerprint(it) } ?: JSONObject.NULL)
          put("binding_state", bindingState)
          put("body_finder_scan_results_for_identity", identity?.let { FabricRuntime.bleSeenCountByIdentity[it]?.get() } ?: 0)
          put("sample_count_5s", fresh.size)
          put("sample_count_8s", retained.size)
          put("last_sample_age_ms", if (last == null) JSONObject.NULL else max(0L, now - last.ms))
          put("latest_rssi_dbm", last?.rssi ?: JSONObject.NULL)
          put("median_rssi_dbm", if (fresh.isEmpty()) JSONObject.NULL else median(fresh.map { it.rssi.toDouble() }))
          put("median_tx_power_dbm", if (fresh.isEmpty()) JSONObject.NULL else median(fresh.map { it.txPower.toDouble() }))
          put("fallback_range_ready", fresh.size >= MIN_SAMPLES_FOR_RANGE)
          put("address_rebind_count", identity?.let { FabricRuntime.addressRebindCountByIdentity[it]?.get() } ?: 0)
          put("blocking_reason", blocker ?: JSONObject.NULL)
        })
      } catch (_: Throwable) {}
    }
    return arr
  }

  private fun bleDiagnostics(ctx: Context, now: Long = System.currentTimeMillis()) = JSONObject().apply {
    put("permissions", JSONObject().apply {
      put("legacy_granted", legacyBluetoothPermissionsGranted(ctx))
      put("modern_granted", modernBluetoothPermissionsGranted(ctx))
      put("location_service_enabled", locationServiceEnabled(ctx) ?: JSONObject.NULL)
    })
    put("scan_state", FabricRuntime.bleScanState)
    put("advertise_state", FabricRuntime.bleAdvertiseState)
    put("scan_mode", FabricRuntime.bleScanMode)
    put("total_scan_results", FabricRuntime.totalScanResults.get())
    put("body_finder_scan_results", FabricRuntime.bodyFinderScanResults.get())
    put("malformed_body_finder_payloads", FabricRuntime.malformedBodyFinderPayloads.get())
    put("self_scan_results_ignored", FabricRuntime.selfScanResultsIgnored.get())
    put("last_any_scan_result_age_ms", ageMs(now, FabricRuntime.lastAnyScanResultWallMs))
    put("last_body_finder_scan_result_age_ms", ageMs(now, FabricRuntime.lastBodyFinderScanResultWallMs))
    put("scan_failure_code", FabricRuntime.bleScanFailureCode ?: JSONObject.NULL)
    put("advertise_failure_code", FabricRuntime.bleAdvertiseFailureCode ?: JSONObject.NULL)
    put("advertise_age_ms", ageMs(now, FabricRuntime.bleAdvertiseStartedWallMs))
    put("advertise_restart_count", FabricRuntime.advertiseRestartCount.get())
    put("active_identity", bleIdentity())
    put("peers", peerBleDiagnostics(now))
    put("system_ranging", if (Build.VERSION.SDK_INT >= 36) SystemRangingApi36.diagnostics(now) else JSONObject().put("state", "UNSUPPORTED").put("detail", "Android API < 36"))
  }

  private fun fabricDiagnostics(now: Long = System.currentTimeMillis()) = JSONObject().apply {
    put("socket_state", FabricRuntime.socketState)
    put("multicast_join_state", FabricRuntime.multicastJoinState)
    put("tx_packets", FabricRuntime.txPackets.get())
    put("rx_packets", FabricRuntime.rxPackets.get())
    put("rx_protocol_v2_packets", FabricRuntime.rxProtocolV2Packets.get())
    put("rx_same_session_packets", FabricRuntime.rxSameSessionPackets.get())
    put("peer_count_active", FabricRuntime.peers.size)
    put("peer_expire_count", FabricRuntime.peerExpireCount.get())
    val peers = JSONArray()
    FabricRuntime.peerPacketCounts.forEach { (nodeId, count) ->
      val lastSeen = FabricRuntime.peerLastSeenWallMs[nodeId]
      peers.put(JSONObject()
        .put("node_id", nodeId)
        .put("last_seen_age_ms", ageMs(now, lastSeen))
        .put("packets_received", count.get())
        .put("state", if (FabricRuntime.peers.containsKey(nodeId)) "ACTIVE" else "EXPIRED"))
    }
    put("peers", peers)
  }

  private fun diagnostics(ctx: Context) = JSONObject()
    .put("ble_diagnostics", bleDiagnostics(ctx))
    .put("fabric_diagnostics", fabricDiagnostics())

  private fun advertisement(ctx: Context) = JSONObject().apply {
    put("protocol_version", PROTOCOL)
    put("session_id", FabricRuntime.sessionId)
    put("node_id", FabricRuntime.nodeId)
    put("display_name", FabricRuntime.displayName)
    put("platform", "android")
    put("monotonic_ns", SystemClock.elapsedRealtimeNanos())
    put("coordinator_score", 0.78)
    put("capabilities", capabilityMap(ctx))
    val rssi = wifiRssi(ctx)
    if (rssi == null) put("rssi_dbm", JSONObject.NULL) else put("rssi_dbm", rssi)
    if (FabricRuntime.baseline == null) put("baseline_rssi_dbm", JSONObject.NULL) else put("baseline_rssi_dbm", FabricRuntime.baseline)
    if (FabricRuntime.sigma == null) put("baseline_sigma_db", JSONObject.NULL) else put("baseline_sigma_db", FabricRuntime.sigma)
    put("position", JSONObject.NULL)
    put("scanning", FabricRuntime.scanning)
    put("ble_identity", bleIdentity())
    put("ranges", rangeObservations())
    put("manual_geometry_override", false)
    val published = FabricRuntime.publishedGeometryJson
    if (published != null) {
      try {
        put("geometry_publisher_node_id", FabricRuntime.nodeId)
        put("published_geometry", JSONObject(published))
      } catch (_: Throwable) {
        put("geometry_publisher_node_id", JSONObject.NULL)
        put("published_geometry", JSONObject.NULL)
      }
    } else {
      put("geometry_publisher_node_id", JSONObject.NULL)
      put("published_geometry", JSONObject.NULL)
    }
  }

  private fun expirePeers(now: Long) {
    val expired = FabricRuntime.peers.entries
      .filter { now - it.value.second > PEER_EXPIRY_MS }
      .map { it.key }
    for (nodeId in expired) {
      if (FabricRuntime.peers.remove(nodeId) != null) FabricRuntime.peerExpireCount.incrementAndGet()
    }
  }

  private fun startNetworkThread(ctx: Context) {
    thread(name = "BodyFinderFabricV2", isDaemon = true) {
      try {
        val socket = MulticastSocket(null)
        socket.reuseAddress = true
        socket.broadcast = true
        socket.bind(InetSocketAddress(PORT))
        FabricRuntime.socketState = "BOUND"
        try {
          socket.joinGroup(InetAddress.getByName(GROUP))
          FabricRuntime.multicastJoinState = "JOINED"
        } catch (e: Throwable) {
          FabricRuntime.multicastJoinState = "FAILED:${e.javaClass.simpleName}"
        }
        socket.soTimeout = 250
        FabricRuntime.socket = socket
        val groupAddress = InetAddress.getByName(GROUP)
        val broadcastAddress = InetAddress.getByName("255.255.255.255")
        val buffer = ByteArray(65507)
        var nextSend = 0L
        var nextSystemRangingRefresh = 0L
        while (FabricRuntime.running) {
          val now = System.currentTimeMillis()
          if (Build.VERSION.SDK_INT >= 36 && now >= nextSystemRangingRefresh && hasPermission(ctx, RANGE_PERMISSION)) {
            try { SystemRangingApi36.refresh(ctx, desiredSystemRangingPeers()) } catch (_: Throwable) {}
            nextSystemRangingRefresh = now + 1_000L
          }
          if (now >= nextSend) {
            val bytes = advertisement(ctx).toString().toByteArray(Charsets.UTF_8)
            try {
              socket.send(DatagramPacket(bytes, bytes.size, groupAddress, PORT))
              FabricRuntime.txPackets.incrementAndGet()
            } catch (_: Throwable) {}
            try {
              socket.send(DatagramPacket(bytes, bytes.size, broadcastAddress, PORT))
              FabricRuntime.txPackets.incrementAndGet()
            } catch (_: Throwable) {}
            nextSend = now + 800L
          }
          try {
            val packet = DatagramPacket(buffer, buffer.size)
            socket.receive(packet)
            FabricRuntime.rxPackets.incrementAndGet()
            val text = String(packet.data, packet.offset, packet.length, Charsets.UTF_8)
            val obj = JSONObject(text)
            if (obj.optInt("protocol_version") == PROTOCOL) FabricRuntime.rxProtocolV2Packets.incrementAndGet()
            val remoteId = obj.optString("node_id")
            if (obj.optInt("protocol_version") == PROTOCOL && obj.optString("session_id") == FabricRuntime.sessionId) {
              FabricRuntime.rxSameSessionPackets.incrementAndGet()
            }
            if (obj.optInt("protocol_version") == PROTOCOL &&
              obj.optString("session_id") == FabricRuntime.sessionId &&
              remoteId.isNotBlank() && remoteId != FabricRuntime.nodeId
            ) {
              val seen = System.currentTimeMillis()
              FabricRuntime.peers[remoteId] = text to seen
              FabricRuntime.peerLastSeenWallMs[remoteId] = seen
              FabricRuntime.peerPacketCounts.computeIfAbsent(remoteId) { AtomicLong(0) }.incrementAndGet()
            }
          } catch (_: java.net.SocketTimeoutException) {
          } catch (_: Throwable) {}
          expirePeers(now)
        }
      } catch (e: Throwable) {
        FabricRuntime.socketState = "FAILED:${e.javaClass.simpleName}"
      } finally {
        if (Build.VERSION.SDK_INT >= 36) {
          try { SystemRangingApi36.stop() } catch (_: Throwable) {}
        }
        try { FabricRuntime.socket?.close() } catch (_: Throwable) {}
        FabricRuntime.socket = null
        FabricRuntime.socketState = "CLOSED"
      }
    }
  }
}
