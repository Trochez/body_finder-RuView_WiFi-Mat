package com.trochez.bodyfindernative

import android.content.Context
import android.content.pm.PackageManager
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
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import kotlin.concurrent.thread

private const val PORT = 47777
private const val GROUP = "239.255.77.77"

private object FabricRuntime {
  @Volatile var running = false
  @Volatile var nodeId = UUID.randomUUID().toString()
  @Volatile var displayName = Build.MODEL ?: "Android"
  @Volatile var sessionId = "body-finder-lab"
  @Volatile var baseline: Double? = null
  @Volatile var sigma: Double? = null
  @Volatile var x: Double? = null
  @Volatile var y: Double? = null
  @Volatile var scanning = false
  var socket: MulticastSocket? = null
  val peers = ConcurrentHashMap<String, Pair<String, Long>>()

  fun stop() {
    running = false
    try { socket?.close() } catch (_: Throwable) {}
    socket = null
    peers.clear()
  }
}

class BodyFinderNativeModule : Module() {
  override fun definition() = ModuleDefinition {
    Name("BodyFinderNative")

    Function("getCapabilitiesJson") {
      val ctx = appContext.reactContext ?: return@Function "{}"
      capabilities(ctx).toString()
    }

    Function("getWifiRssi") {
      val ctx = appContext.reactContext ?: return@Function null
      wifiRssi(ctx)
    }

    Function("updateLocalState") { baseline: Double?, sigma: Double?, x: Double?, y: Double?, scanning: Boolean ->
      FabricRuntime.baseline = baseline
      FabricRuntime.sigma = sigma
      FabricRuntime.x = x
      FabricRuntime.y = y
      FabricRuntime.scanning = scanning
      true
    }

    AsyncFunction("startFabric") { nodeId: String?, displayName: String?, sessionId: String? ->
      val ctx = appContext.reactContext ?: return@AsyncFunction false
      FabricRuntime.stop()
      FabricRuntime.nodeId = nodeId?.takeIf { it.isNotBlank() } ?: UUID.randomUUID().toString()
      FabricRuntime.displayName = displayName?.takeIf { it.isNotBlank() } ?: (Build.MODEL ?: "Android")
      FabricRuntime.sessionId = sessionId?.takeIf { it.isNotBlank() } ?: "body-finder-lab"
      FabricRuntime.running = true
      startNetworkThread(ctx.applicationContext)
      true
    }

    Function("stopFabric") {
      FabricRuntime.stop()
      true
    }

    Function("getPeersJson") {
      val now = System.currentTimeMillis()
      FabricRuntime.peers.entries.removeIf { now - it.value.second > 5000 }
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

  private fun capabilities(ctx: Context): JSONObject {
    val pm = ctx.packageManager
    val wifi = ctx.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
    return JSONObject().apply {
      put("platform", "android")
      put("manufacturer", Build.MANUFACTURER ?: "unknown")
      put("model", Build.MODEL ?: "unknown")
      put("android_api", Build.VERSION.SDK_INT)
      put("wifi", state(wifi != null && wifi.isWifiEnabled, "Wi-Fi manager enabled"))
      put("wifi_rssi", state(wifiRssi(ctx) != null, "live connected-link RSSI read"))
      put("wifi_rtt", if (Build.VERSION.SDK_INT >= 28 && pm.hasSystemFeature(PackageManager.FEATURE_WIFI_RTT)) {
        JSONObject().put("state", "SUPPORTED_UNVERIFIED").put("detail", "Wi-Fi RTT feature present; real AP ranging must be validated in field")
      } else state(false, "Wi-Fi RTT feature absent"))
      put("ble", if (pm.hasSystemFeature(PackageManager.FEATURE_BLUETOOTH_LE)) {
        JSONObject().put("state", "SUPPORTED_UNVERIFIED").put("detail", "BLE hardware present; BLE ranging not used as human evidence in this build")
      } else state(false, "BLE feature absent"))
      put("imu", state(pm.hasSystemFeature(PackageManager.FEATURE_SENSOR_ACCELEROMETER), "accelerometer feature"))
      put("csi", JSONObject().put("state", "UNSUPPORTED").put("detail", "No public/verified CSI adapter loaded; RSSI is never labeled CSI"))
      put("udp_fabric", JSONObject().put("state", "WORKING_DEGRADED").put("detail", "local UDP multicast/broadcast; verify on actual LAN"))
    }
  }

  private fun state(ok: Boolean, detail: String): JSONObject = JSONObject()
    .put("state", if (ok) "WORKING" else "UNSUPPORTED")
    .put("detail", detail)

  @Suppress("DEPRECATION")
  private fun wifiRssi(ctx: Context): Double? {
    return try {
      val wm = ctx.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
      if (!wm.isWifiEnabled) null else wm.connectionInfo?.rssi?.toDouble()?.takeIf { it in -127.0..0.0 }
    } catch (_: Throwable) { null }
  }

  private fun advertisement(ctx: Context): JSONObject {
    return JSONObject().apply {
      put("protocol_version", 1)
      put("session_id", FabricRuntime.sessionId)
      put("node_id", FabricRuntime.nodeId)
      put("display_name", FabricRuntime.displayName)
      put("platform", "android")
      put("monotonic_ns", SystemClock.elapsedRealtimeNanos())
      put("coordinator_score", 0.78)
      put("capabilities", capabilities(ctx))
      val rssi = wifiRssi(ctx)
      if (rssi == null) put("rssi_dbm", JSONObject.NULL) else put("rssi_dbm", rssi)
      if (FabricRuntime.baseline == null) put("baseline_rssi_dbm", JSONObject.NULL) else put("baseline_rssi_dbm", FabricRuntime.baseline)
      if (FabricRuntime.sigma == null) put("baseline_sigma_db", JSONObject.NULL) else put("baseline_sigma_db", FabricRuntime.sigma)
      if (FabricRuntime.x != null && FabricRuntime.y != null) {
        put("position", JSONObject().put("x_m", FabricRuntime.x).put("y_m", FabricRuntime.y).put("z_m", 0.0).put("sigma_m", 0.25))
      } else put("position", JSONObject.NULL)
      put("scanning", FabricRuntime.scanning)
    }
  }

  private fun startNetworkThread(ctx: Context) {
    thread(name = "BodyFinderFabric", isDaemon = true) {
      try {
        val s = MulticastSocket(null)
        s.reuseAddress = true
        s.broadcast = true
        s.bind(InetSocketAddress(PORT))
        try { s.joinGroup(InetAddress.getByName(GROUP)) } catch (_: Throwable) {}
        s.soTimeout = 250
        FabricRuntime.socket = s
        val groupAddr = InetAddress.getByName(GROUP)
        val broadcastAddr = InetAddress.getByName("255.255.255.255")
        val buffer = ByteArray(65507)
        var nextSend = 0L
        while (FabricRuntime.running) {
          val now = System.currentTimeMillis()
          if (now >= nextSend) {
            val bytes = advertisement(ctx).toString().toByteArray(Charsets.UTF_8)
            try { s.send(DatagramPacket(bytes, bytes.size, groupAddr, PORT)) } catch (_: Throwable) {}
            try { s.send(DatagramPacket(bytes, bytes.size, broadcastAddr, PORT)) } catch (_: Throwable) {}
            nextSend = now + 1000
          }
          try {
            val packet = DatagramPacket(buffer, buffer.size)
            s.receive(packet)
            val text = String(packet.data, packet.offset, packet.length, Charsets.UTF_8)
            val obj = JSONObject(text)
            val remoteSession = obj.optString("session_id")
            val remoteId = obj.optString("node_id")
            if (obj.optInt("protocol_version") == 1 && remoteSession == FabricRuntime.sessionId && remoteId.isNotBlank() && remoteId != FabricRuntime.nodeId) {
              FabricRuntime.peers[remoteId] = text to System.currentTimeMillis()
            }
          } catch (_: java.net.SocketTimeoutException) {
          } catch (_: Throwable) {
          }
        }
      } catch (_: Throwable) {
      } finally {
        try { FabricRuntime.socket?.close() } catch (_: Throwable) {}
        FabricRuntime.socket = null
      }
    }
  }
}
