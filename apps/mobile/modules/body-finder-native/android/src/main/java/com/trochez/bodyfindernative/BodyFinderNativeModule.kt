package com.trochez.bodyfindernative

import android.Manifest
import android.bluetooth.BluetoothManager
import android.bluetooth.le.AdvertiseCallback
import android.bluetooth.le.AdvertiseData
import android.bluetooth.le.AdvertiseSettings
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
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
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.ConcurrentLinkedDeque
import kotlin.concurrent.thread
import kotlin.math.max
import kotlin.math.pow

private const val PORT=47777
private const val GROUP="239.255.77.77"
private const val PROTOCOL=2
private const val MANUFACTURER_ID=0x05F1
private const val RANGE_PERMISSION="android.permission.RANGING"
private data class RssiSample(val rssi:Int,val txPower:Int,val ms:Long)

private object FabricRuntime{
 @Volatile var running=false
 @Volatile var nodeId=UUID.randomUUID().toString()
 @Volatile var displayName=Build.MODEL?:"Android"
 @Volatile var sessionId="body-finder-lab"
 @Volatile var baseline:Double?=null
 @Volatile var sigma:Double?=null
 @Volatile var scanning=false
 @Volatile var bleScanning=false
 @Volatile var bleAdvertising=false
 @Volatile var bleDetail="BLE not started"
 var socket:MulticastSocket?=null
 val peers=ConcurrentHashMap<String,Pair<String,Long>>()
 val rssiWindows=ConcurrentHashMap<String,ConcurrentLinkedDeque<RssiSample>>()
 var advertiser:android.bluetooth.le.BluetoothLeAdvertiser?=null
 var scanner:android.bluetooth.le.BluetoothLeScanner?=null
 var advertiseCallback:AdvertiseCallback?=null
 var scanCallback:ScanCallback?=null
 fun stopBle(){try{advertiseCallback?.let{advertiser?.stopAdvertising(it)}}catch(_:Throwable){};try{scanCallback?.let{scanner?.stopScan(it)}}catch(_:Throwable){};advertiser=null;scanner=null;advertiseCallback=null;scanCallback=null;bleScanning=false;bleAdvertising=false;rssiWindows.clear()}
 fun stop(){running=false;try{socket?.close()}catch(_:Throwable){};socket=null;peers.clear();stopBle()}
}

class BodyFinderNativeModule:Module(){
 override fun definition()=ModuleDefinition{
  Name("BodyFinderNative")
  Function("getCapabilitiesJson"){val ctx=appContext.reactContext?:return@Function "{}";deviceReport(ctx).toString()}
  Function("getWifiRssi"){val ctx=appContext.reactContext?:return@Function null;wifiRssi(ctx)}
  Function("updateLocalState"){baseline:Double?,sigma:Double?,scanning:Boolean->FabricRuntime.baseline=baseline;FabricRuntime.sigma=sigma;FabricRuntime.scanning=scanning;true}
  AsyncFunction("startFabric"){nodeId:String?,displayName:String?,sessionId:String?->
   val ctx=appContext.reactContext?:return@AsyncFunction false;FabricRuntime.stop();val prefs=ctx.getSharedPreferences("body-finder-runtime",Context.MODE_PRIVATE);val saved=prefs.getString("node-id-v2",null);val chosen=nodeId?.takeIf{it.isNotBlank()}?:saved?:UUID.randomUUID().toString().also{prefs.edit().putString("node-id-v2",it).apply()};FabricRuntime.nodeId=chosen;FabricRuntime.displayName=displayName?.takeIf{it.isNotBlank()}?:(Build.MODEL?:"Android");FabricRuntime.sessionId=sessionId?.takeIf{it.isNotBlank()}?:"body-finder-lab";FabricRuntime.running=true;startBle(ctx.applicationContext);startNetworkThread(ctx.applicationContext);true
  }
  Function("stopFabric"){FabricRuntime.stop();true}
  Function("getPeersJson"){val now=System.currentTimeMillis();FabricRuntime.peers.entries.removeIf{now-it.value.second>5000};val arr=JSONArray();FabricRuntime.peers.values.forEach{pair->try{arr.put(JSONObject(pair.first))}catch(_:Throwable){}};arr.toString()}
  Function("getLocalAdvertisementJson"){val ctx=appContext.reactContext?:return@Function "{}";advertisement(ctx).toString()}
 }
 private fun probe(state:String,detail:String)=JSONObject().put("state",state).put("detail",detail)
 private fun hasPermission(ctx:Context,permission:String)=Build.VERSION.SDK_INT<23||ctx.checkSelfPermission(permission)==PackageManager.PERMISSION_GRANTED
 private fun state(ok:Boolean,detail:String)=probe(if(ok)"WORKING"else"UNSUPPORTED",detail)
 private fun deviceReport(ctx:Context)=JSONObject().apply{put("platform","android");put("manufacturer",Build.MANUFACTURER?:"unknown");put("model",Build.MODEL?:"unknown");put("android_api",Build.VERSION.SDK_INT);put("capabilities",capabilityMap(ctx))}
 private fun capabilityMap(ctx:Context):JSONObject{
  val pm=ctx.packageManager;val wifi=ctx.applicationContext.getSystemService(Context.WIFI_SERVICE)as?WifiManager;val bleFeature=pm.hasSystemFeature(PackageManager.FEATURE_BLUETOOTH_LE);val blePerm=Build.VERSION.SDK_INT<31||(hasPermission(ctx,Manifest.permission.BLUETOOTH_SCAN)&&hasPermission(ctx,Manifest.permission.BLUETOOTH_ADVERTISE))
  return JSONObject().apply{
   put("wifi",state(wifi!=null&&wifi.isWifiEnabled,"Wi-Fi manager enabled"));put("wifi_rssi",state(wifiRssi(ctx)!=null,"live connected-link RSSI; human-presence evidence only, never inter-node distance"));put("wifi_rtt",if(Build.VERSION.SDK_INT>=28&&pm.hasSystemFeature(PackageManager.FEATURE_WIFI_RTT))probe("SUPPORTED_UNVERIFIED","Wi-Fi RTT feature present; peer/AP ranging is not claimed until a live session reports measurements")else state(false,"Wi-Fi RTT feature absent"));put("android_ranging_api",androidRangingProbe(ctx));put("ble",if(!bleFeature)state(false,"BLE feature absent")else if(!blePerm)probe("PERMISSION_REQUIRED","Bluetooth scan/advertise permission required")else probe("WORKING","BLE hardware and permissions available"));put("ble_peer_ranging",when{!bleFeature->probe("UNSUPPORTED","BLE feature absent");!blePerm->probe("PERMISSION_REQUIRED","Bluetooth permissions required");FabricRuntime.bleScanning->probe("WORKING_DEGRADED",FabricRuntime.bleDetail+"; distance uses a conservative RSSI path-loss model and large sigma");else->probe("SUPPORTED_UNVERIFIED",FabricRuntime.bleDetail)});put("imu",state(pm.hasSystemFeature(PackageManager.FEATURE_SENSOR_ACCELEROMETER),"accelerometer feature"));put("automatic_geometry_compute",probe("WORKING","protocol-v2 automatic geometry solver runs in the app"));put("csi",probe("UNSUPPORTED","No public/verified CSI adapter loaded; RSSI is never labeled CSI"));put("udp_fabric",probe("WORKING_DEGRADED","local UDP multicast/broadcast; verify on the actual LAN"));put("compute",probe("WORKING","Android Body Finder application runtime"))
  }
 }
 private fun androidRangingProbe(ctx:Context):JSONObject{
  if(Build.VERSION.SDK_INT<36)return probe("UNSUPPORTED","android.ranging.RangingManager requires Android API 36+")
  return try{val clazz=Class.forName("android.ranging.RangingManager");val method=Context::class.java.getMethod("getSystemService",Class::class.java);val service=method.invoke(ctx,clazz);if(service==null)probe("UNSUPPORTED","RangingManager service unavailable")else if(!hasPermission(ctx,RANGE_PERMISSION))probe("PERMISSION_REQUIRED","android.permission.RANGING is required")else probe("SUPPORTED_UNVERIFIED","RangingManager present and permission granted; advanced UWB/CS/NAN-RTT availability is device/session dependent. BLE-RSSI fallback remains the verified live peer input in this release")}catch(e:Throwable){probe("PROBE_FAILED","RangingManager probe failed: ${e.javaClass.simpleName}")}
 }
 @Suppress("DEPRECATION") private fun wifiRssi(ctx:Context):Double?=try{val wm=ctx.applicationContext.getSystemService(Context.WIFI_SERVICE)as WifiManager;if(!wm.isWifiEnabled)null else wm.connectionInfo?.rssi?.toDouble()?.takeIf{it in -126.0..0.0}}catch(_:Throwable){null}
 private fun bleIdentity(nodeId:String=FabricRuntime.nodeId):String{val bytes=MessageDigest.getInstance("SHA-256").digest(nodeId.toByteArray(Charsets.UTF_8)).copyOfRange(0,8);return bytes.joinToString(""){"%02x".format(it.toInt()and 0xff)}}
 private fun blePayload():ByteArray{val id=bleIdentity();val out=ByteArray(10);out[0]=0x42;out[1]=0x46;for(i in 0 until 8)out[i+2]=id.substring(i*2,i*2+2).toInt(16).toByte();return out}
 private fun payloadIdentity(data:ByteArray?):String?{if(data==null||data.size<10||data[0]!=0x42.toByte()||data[1]!=0x46.toByte())return null;return data.copyOfRange(2,10).joinToString(""){"%02x".format(it.toInt()and 0xff)}}
 private fun startBle(ctx:Context){
  try{val manager=ctx.getSystemService(Context.BLUETOOTH_SERVICE)as?BluetoothManager?:run{FabricRuntime.bleDetail="BluetoothManager unavailable";return};val adapter=manager.adapter?:run{FabricRuntime.bleDetail="Bluetooth adapter unavailable";return};if(!adapter.isEnabled){FabricRuntime.bleDetail="Bluetooth disabled";return};if(Build.VERSION.SDK_INT>=31&&(!hasPermission(ctx,Manifest.permission.BLUETOOTH_SCAN)||!hasPermission(ctx,Manifest.permission.BLUETOOTH_ADVERTISE))){FabricRuntime.bleDetail="Bluetooth scan/advertise permission required";return};val scanner=adapter.bluetoothLeScanner?:run{FabricRuntime.bleDetail="BLE scanner unavailable";return};val advertiser=adapter.bluetoothLeAdvertiser;FabricRuntime.scanner=scanner;FabricRuntime.advertiser=advertiser
   val scanCb=object:ScanCallback(){override fun onScanResult(callbackType:Int,result:ScanResult){recordScan(result)};override fun onBatchScanResults(results:MutableList<ScanResult>){results.forEach{recordScan(it)}};override fun onScanFailed(errorCode:Int){FabricRuntime.bleScanning=false;FabricRuntime.bleDetail="BLE scan failed code=$errorCode"}}
   FabricRuntime.scanCallback=scanCb;scanner.startScan(scanCb);FabricRuntime.bleScanning=true
   if(advertiser!=null){val advCb=object:AdvertiseCallback(){override fun onStartSuccess(settingsInEffect:AdvertiseSettings){FabricRuntime.bleAdvertising=true;FabricRuntime.bleDetail="BLE scan + Body Finder advertisement active"};override fun onStartFailure(errorCode:Int){FabricRuntime.bleAdvertising=false;FabricRuntime.bleDetail="BLE scan active; advertisement unavailable code=$errorCode"}};FabricRuntime.advertiseCallback=advCb;val settings=AdvertiseSettings.Builder().setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_LATENCY).setTxPowerLevel(AdvertiseSettings.ADVERTISE_TX_POWER_MEDIUM).setConnectable(false).build();val data=AdvertiseData.Builder().addManufacturerData(MANUFACTURER_ID,blePayload()).setIncludeTxPowerLevel(true).build();advertiser.startAdvertising(settings,data,advCb)}else FabricRuntime.bleDetail="BLE scan active; peripheral advertising unsupported on this device"
  }catch(e:SecurityException){FabricRuntime.bleDetail="BLE permission denied: ${e.message}"}catch(e:Throwable){FabricRuntime.bleDetail="BLE start failed: ${e.javaClass.simpleName}"}
 }
 private fun recordScan(result:ScanResult){val id=payloadIdentity(result.scanRecord?.getManufacturerSpecificData(MANUFACTURER_ID))?:return;if(id==bleIdentity())return;val tx=result.scanRecord?.txPowerLevel?.takeIf{it in -100..20}?:-59;val now=System.currentTimeMillis();val q=FabricRuntime.rssiWindows.computeIfAbsent(id){ConcurrentLinkedDeque()};q.addLast(RssiSample(result.rssi,tx,now));while(q.size>21)q.pollFirst();while(true){val first=q.peekFirst()?:break;if(now-first.ms<=8000)break else q.pollFirst()}}
 private fun median(values:List<Double>):Double{val xs=values.sorted();val n=xs.size;return if(n%2==0)(xs[n/2-1]+xs[n/2])/2.0 else xs[n/2]}
 private fun rangeObservations():JSONArray{
  val arr=JSONArray();val now=System.currentTimeMillis();val mono=SystemClock.elapsedRealtimeNanos();FabricRuntime.peers.values.forEach{pair->try{val peer=JSONObject(pair.first);val peerId=peer.optString("node_id");val bid=peer.optString("ble_identity").takeIf{it.isNotBlank()&&it!="null"}?:return@forEach;val samples=FabricRuntime.rssiWindows[bid]?.filter{now-it.ms<=5000}?:emptyList();if(samples.size<3)return@forEach;val rssi=median(samples.map{it.rssi.toDouble()});val tx=median(samples.map{it.txPower.toDouble()});val pathLossN=2.2;val distance=10.0.pow((tx-rssi)/(10.0*pathLossN)).coerceIn(0.20,30.0);val sigma=max(1.5,distance*0.75);arr.put(JSONObject().put("session_id",FabricRuntime.sessionId).put("observer_node_id",FabricRuntime.nodeId).put("peer_node_id",peerId).put("technology","BLE_RSSI").put("monotonic_ns",mono).put("distance_m",distance).put("distance_sigma_m",sigma).put("azimuth_deg",JSONObject.NULL).put("azimuth_sigma_deg",JSONObject.NULL).put("elevation_deg",JSONObject.NULL).put("elevation_sigma_deg",JSONObject.NULL).put("rssi_dbm",rssi).put("quality","LOW").put("source_detail","Live BLE advertisement RSSI; median ${samples.size} samples; advertised/fallback Tx=$tx dBm; path-loss n=$pathLossN; intentionally large uncertainty; not UWB/RTT/CSI"))}catch(_:Throwable){}};return arr
 }
 private fun advertisement(ctx:Context)=JSONObject().apply{put("protocol_version",PROTOCOL);put("session_id",FabricRuntime.sessionId);put("node_id",FabricRuntime.nodeId);put("display_name",FabricRuntime.displayName);put("platform","android");put("monotonic_ns",SystemClock.elapsedRealtimeNanos());put("coordinator_score",0.78);put("capabilities",capabilityMap(ctx));val rssi=wifiRssi(ctx);if(rssi==null)put("rssi_dbm",JSONObject.NULL)else put("rssi_dbm",rssi);if(FabricRuntime.baseline==null)put("baseline_rssi_dbm",JSONObject.NULL)else put("baseline_rssi_dbm",FabricRuntime.baseline);if(FabricRuntime.sigma==null)put("baseline_sigma_db",JSONObject.NULL)else put("baseline_sigma_db",FabricRuntime.sigma);put("position",JSONObject.NULL);put("scanning",FabricRuntime.scanning);put("ble_identity",bleIdentity());put("ranges",rangeObservations());put("manual_geometry_override",false)}
 private fun startNetworkThread(ctx:Context){thread(name="BodyFinderFabricV2",isDaemon=true){try{val s=MulticastSocket(null);s.reuseAddress=true;s.broadcast=true;s.bind(InetSocketAddress(PORT));try{s.joinGroup(InetAddress.getByName(GROUP))}catch(_:Throwable){};s.soTimeout=250;FabricRuntime.socket=s;val groupAddr=InetAddress.getByName(GROUP);val broadcastAddr=InetAddress.getByName("255.255.255.255");val buffer=ByteArray(65507);var nextSend=0L;while(FabricRuntime.running){val now=System.currentTimeMillis();if(now>=nextSend){val bytes=advertisement(ctx).toString().toByteArray(Charsets.UTF_8);try{s.send(DatagramPacket(bytes,bytes.size,groupAddr,PORT))}catch(_:Throwable){};try{s.send(DatagramPacket(bytes,bytes.size,broadcastAddr,PORT))}catch(_:Throwable){};nextSend=now+800};try{val packet=DatagramPacket(buffer,buffer.size);s.receive(packet);val text=String(packet.data,packet.offset,packet.length,Charsets.UTF_8);val obj=JSONObject(text);val remoteId=obj.optString("node_id");if(obj.optInt("protocol_version")==PROTOCOL&&obj.optString("session_id")==FabricRuntime.sessionId&&remoteId.isNotBlank()&&remoteId!=FabricRuntime.nodeId)FabricRuntime.peers[remoteId]=text to System.currentTimeMillis()}catch(_:java.net.SocketTimeoutException){}catch(_:Throwable){}}}catch(_:Throwable){}finally{try{FabricRuntime.socket?.close()}catch(_:Throwable){};FabricRuntime.socket=null}}}
}
