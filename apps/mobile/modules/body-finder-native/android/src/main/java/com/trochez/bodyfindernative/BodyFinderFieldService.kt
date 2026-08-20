package com.trochez.bodyfindernative

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.net.wifi.WifiManager
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import org.json.JSONObject
import java.util.concurrent.atomic.AtomicLong

internal object FieldServiceState {
  @Volatile var state: String = "STOPPED"
  @Volatile var startedWallMs: Long? = null
  @Volatile var wakeLockHeld: Boolean = false
  @Volatile var wifiLockHeld: Boolean = false
  @Volatile var multicastLockHeld: Boolean = false
  @Volatile var lastError: String? = null
  val startCount = AtomicLong(0)
  val stopCount = AtomicLong(0)

  fun diagnostics(context: android.content.Context): JSONObject {
    val pm = context.getSystemService(PowerManager::class.java)
    return JSONObject()
      .put("foreground_service_state", state)
      .put("foreground_service_age_ms", startedWallMs?.let { (System.currentTimeMillis() - it).coerceAtLeast(0) } ?: JSONObject.NULL)
      .put("start_count", startCount.get())
      .put("stop_count", stopCount.get())
      .put("screen_state", if (pm?.isInteractive == true) "ON" else "OFF")
      .put("power_save_mode", pm?.isPowerSaveMode ?: false)
      .put("device_idle_mode", if (Build.VERSION.SDK_INT >= 23) (pm?.isDeviceIdleMode ?: false) else false)
      .put("wake_lock_held", wakeLockHeld)
      .put("wifi_lock_held", wifiLockHeld)
      .put("multicast_lock_held", multicastLockHeld)
      .put("last_error", lastError ?: JSONObject.NULL)
  }
}

class BodyFinderFieldService : Service() {
  companion object {
    private const val CHANNEL_ID = "body_finder_field_session"
    private const val NOTIFICATION_ID = 47777
    const val ACTION_START = "com.trochez.bodyfindernative.START_FIELD_SESSION"
    const val ACTION_STOP = "com.trochez.bodyfindernative.STOP_FIELD_SESSION"
  }

  private var wakeLock: PowerManager.WakeLock? = null
  private var wifiLock: WifiManager.WifiLock? = null
  private var multicastLock: WifiManager.MulticastLock? = null

  override fun onBind(intent: Intent?): IBinder? = null

  override fun onCreate() {
    super.onCreate()
    createChannel()
  }

  override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
    if (intent?.action == ACTION_STOP) {
      stopFieldSession()
      stopSelf()
      return START_NOT_STICKY
    }
    try {
      startForeground(NOTIFICATION_ID, notification())
      acquireLocks()
      FieldServiceState.state = "RUNNING"
      FieldServiceState.startedWallMs = FieldServiceState.startedWallMs ?: System.currentTimeMillis()
      FieldServiceState.startCount.incrementAndGet()
      FieldServiceState.lastError = null
    } catch (e: Throwable) {
      FieldServiceState.state = "FAILED"
      FieldServiceState.lastError = "${e.javaClass.simpleName}: ${e.message}"
    }
    return START_STICKY
  }

  override fun onDestroy() {
    stopFieldSession()
    super.onDestroy()
  }

  private fun stopFieldSession() {
    releaseLocks()
    FieldServiceState.state = "STOPPED"
    FieldServiceState.startedWallMs = null
    FieldServiceState.stopCount.incrementAndGet()
    try { stopForeground(STOP_FOREGROUND_REMOVE) } catch (_: Throwable) {}
  }

  private fun acquireLocks() {
    val pm = getSystemService(PowerManager::class.java)
    if (wakeLock?.isHeld != true) {
      wakeLock = pm?.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "BodyFinder::FieldSession")?.apply {
        setReferenceCounted(false)
        acquire()
      }
    }
    FieldServiceState.wakeLockHeld = wakeLock?.isHeld == true

    val wm = applicationContext.getSystemService(WifiManager::class.java)
    if (wifiLock?.isHeld != true) {
      @Suppress("DEPRECATION")
      val created = wm?.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "BodyFinder::Wifi")
      created?.setReferenceCounted(false)
      created?.acquire()
      wifiLock = created
    }
    FieldServiceState.wifiLockHeld = wifiLock?.isHeld == true

    if (multicastLock?.isHeld != true) {
      val created = wm?.createMulticastLock("BodyFinder::Multicast")
      created?.setReferenceCounted(false)
      created?.acquire()
      multicastLock = created
    }
    FieldServiceState.multicastLockHeld = multicastLock?.isHeld == true
  }

  private fun releaseLocks() {
    try { if (wakeLock?.isHeld == true) wakeLock?.release() } catch (_: Throwable) {}
    try { if (wifiLock?.isHeld == true) wifiLock?.release() } catch (_: Throwable) {}
    try { if (multicastLock?.isHeld == true) multicastLock?.release() } catch (_: Throwable) {}
    wakeLock = null
    wifiLock = null
    multicastLock = null
    FieldServiceState.wakeLockHeld = false
    FieldServiceState.wifiLockHeld = false
    FieldServiceState.multicastLockHeld = false
  }

  private fun createChannel() {
    if (Build.VERSION.SDK_INT < 26) return
    val manager = getSystemService(NotificationManager::class.java) ?: return
    manager.createNotificationChannel(
      NotificationChannel(
        CHANNEL_ID,
        "Body Finder active field session",
        NotificationManager.IMPORTANCE_LOW,
      ).apply {
        description = "Keeps Body Finder RF discovery and field networking active during a validation/search session."
        setShowBadge(false)
      }
    )
  }

  private fun notification(): Notification {
    val icon = if (applicationInfo.icon != 0) applicationInfo.icon else android.R.drawable.stat_notify_sync
    val builder = if (Build.VERSION.SDK_INT >= 26) {
      Notification.Builder(this, CHANNEL_ID)
    } else {
      @Suppress("DEPRECATION")
      Notification.Builder(this)
    }
    return builder
      .setSmallIcon(icon)
      .setContentTitle("Body Finder – active field session")
      .setContentText("BLE/UDP sensing is being kept active. Stop the session in Body Finder when finished.")
      .setOngoing(true)
      .setCategory(Notification.CATEGORY_SERVICE)
      .build()
  }
}
