#!/usr/bin/env python3
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt'
s=p.read_text(encoding='utf-8')
old='''    val validRssi = BleRangeEstimator.isValidBleRssi(result.rssi.toDouble())\n    if (validRssi && BleAcquisitionPolicy.currentStrategy() == BleAcquisitionStrategy.UNFILTERED_RECOVERY) ValidationEventLog.record("FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY", "BODY_FINDER_CALLBACK", now = now)'''
new='''    val validRssi = BleRangeEstimator.isValidBleRssi(result.rssi.toDouble())\n    if (validRssi && BleAcquisitionPolicy.currentStrategy() == BleAcquisitionStrategy.UNFILTERED_RECOVERY) {\n      val callbackPeerId = FabricRuntime.peers.values.firstNotNullOfOrNull { pair ->\n        try {\n          val peer=JSONObject(pair.first)\n          if(peer.optString("ble_identity")==id) peer.optString("node_id").takeIf { it.isNotBlank() } else null\n        } catch(_:Throwable) { null }\n      }\n      if(callbackPeerId!=null) BleAcquisitionPolicy.noteValidCallback(callbackPeerId,now)\n    }'''
if old in s:
    p.write_text(s.replace(old,new,1),encoding='utf-8')
elif 'callbackPeerId = FabricRuntime.peers.values.firstNotNullOfOrNull' not in s:
    raise SystemExit('recordScan target callback pattern not found')
print('dev12 target callback fix complete')
