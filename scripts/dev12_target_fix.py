#!/usr/bin/env python3
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt'
s=p.read_text(encoding='utf-8')
old='''    val validRssi = BleRangeEstimator.isValidBleRssi(result.rssi.toDouble())\n    if (validRssi && BleAcquisitionPolicy.currentStrategy() == BleAcquisitionStrategy.UNFILTERED_RECOVERY) ValidationEventLog.record("FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY", "BODY_FINDER_CALLBACK", now = now)'''
new='''    val validRssi = BleRangeEstimator.isValidBleRssi(result.rssi.toDouble())\n    if (validRssi && BleAcquisitionPolicy.currentStrategy() == BleAcquisitionStrategy.UNFILTERED_RECOVERY) {\n      val callbackPeerId = FabricRuntime.peers.values.firstNotNullOfOrNull { pair ->\n        try {\n          val peer=JSONObject(pair.first)\n          if(peer.optString("ble_identity")==id) peer.optString("node_id").takeIf { it.isNotBlank() } else null\n        } catch(_:Throwable) { null }\n      }\n      if(callbackPeerId!=null) BleAcquisitionPolicy.noteValidCallback(callbackPeerId,now)\n    }'''
if old in s: s=s.replace(old,new,1)
elif 'callbackPeerId = FabricRuntime.peers.values.firstNotNullOfOrNull' not in s: raise SystemExit('recordScan target callback pattern not found')

if 'private fun validationStartIssues' not in s:
    marker='''  private fun deviceReport(ctx: Context) = JSONObject().apply {'''
    helper='''  private fun validationStartIssues(ctx:Context):List<String> {\n    val issues=validationEnvironmentIssues(ctx).toMutableList()\n    if(Build.VERSION.SDK_INT < 31 && locationServiceEnabled(ctx)==false) issues += "LOCATION_OFF"\n    if(expectedKnownPeerCount()<2) issues += "EXPECTED_BLE_PEERS_LT_2"\n    if(BleAcquisitionPolicy.currentStrategy()!=BleAcquisitionStrategy.FILTERED_PRIMARY) issues += "NOT_FILTERED_PRIMARY"\n    if(FabricRuntime.bleScanning && BleAcquisitionPolicy.currentStrategy()==BleAcquisitionStrategy.FILTERED_PRIMARY && FabricRuntime.bleScanMode!="LOW_LATENCY") issues += "SCAN_MODE_NOT_LOW_LATENCY"\n    return issues.distinct()\n  }\n\n  private fun deviceReport(ctx: Context) = JSONObject().apply {'''
    if marker not in s: raise SystemExit('deviceReport marker not found')
    s=s.replace(marker,helper,1)

s=s.replace('''      val issues = validationEnvironmentIssues(ctx)\n      if (issues.isNotEmpty()) return@Function "VALIDATION_ENVIRONMENT_INVALID:${issues.joinToString(",")}"''','''      val issues = validationStartIssues(ctx)\n      if (issues.isNotEmpty()) return@Function "VALIDATION_PREFLIGHT_INVALID:${issues.joinToString(",")}"''',1)
s=s.replace('''    val issues=validationEnvironmentIssues(ctx)\n    val manager=ctx.getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager''','''    val issues=validationStartIssues(ctx)\n    val manager=ctx.getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager''',1)

p.write_text(s,encoding='utf-8')
print('dev12 target/preflight fix complete')
