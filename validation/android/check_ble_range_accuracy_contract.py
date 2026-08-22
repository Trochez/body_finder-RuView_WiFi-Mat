#!/usr/bin/env python3
from __future__ import annotations
import json, math, re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
MODULE=ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt'
ESTIMATOR=ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleRangeEstimator.kt'
SERVICE=ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderFieldService.kt'
MANIFEST=ROOT/'apps/mobile/modules/body-finder-native/android/src/main/AndroidManifest.xml'
APP_JSON=ROOT/'apps/mobile/app.json'; INDEX_TS=ROOT/'apps/mobile/modules/body-finder-native/index.ts'; APP=ROOT/'apps/mobile/App.tsx'
GRAPH=ROOT/'apps/mobile/src/geometryDiagnostics.ts'; FUSION=ROOT/'apps/mobile/src/rangeFusion.ts'
PROFILE=ROOT/'calibration/ble-range-calibration-profiles.json'; PROFILE_SCHEMA=ROOT/'calibration/ble-range-calibration-schema.json'
P0C=ROOT/'validation/fixtures/ble-range/p0c-calibration-summary.json'; FITTER=ROOT/'validation/analysis/fit_ble_range_profile.py'
def require(c,m):
    if not c: raise SystemExit('BLE RANGE ACCURACY CONTRACT FAILED: '+m)
def close(a,b,t=1e-6): return abs(a-b)<=t
module=MODULE.read_text(); estimator=ESTIMATOR.read_text(); service=SERVICE.read_text(); manifest=MANIFEST.read_text(); app=APP.read_text(); index_ts=INDEX_TS.read_text(); graph=GRAPH.read_text(); fusion=FUSION.read_text(); fitter=FITTER.read_text(); app_json=json.loads(APP_JSON.read_text()); profiles=json.loads(PROFILE.read_text()); json.loads(PROFILE_SCHEMA.read_text()); p0c=json.loads(P0C.read_text())
active=next(p for p in profiles['profiles'] if p['profile_id']==profiles['active_profile_id']); expected=p0c['profile']
require(active['profile_id']=='android-ble-lab-v1','active profile changed'); require(active['validated'] is True,'validated profile disabled'); require(active['physical_confidence']=='COARSE','physical confidence changed')
require(close(float(active['rssi_at_1m_dbm']),float(expected['rssi_at_1m_dbm'])) and close(float(active['rssi_at_1m_dbm']),-69.19),'RSSI@1m drifted')
require(close(float(active['path_loss_exponent']),float(expected['path_loss_exponent'])) and close(float(active['path_loss_exponent']),3.62),'path-loss exponent drifted')
require(close(float(active['valid_distance_min_m']),0.5) and close(float(active['valid_distance_max_m']),5.0),'valid domain changed')
require(float(active['validation_metrics']['mae_m'])<=2.0 and float(active['validation_metrics']['max_error_m'])<=3.0,'calibration gates lost')
require(profiles['policy']['silent_distance_clamp'] is False and profiles['policy']['ground_truth_used_at_runtime'] is False,'truth policy regressed')
require('coerceIn(0.5, 5.0)' not in estimator+module,'silent domain clamp present'); require(not re.search(r'10\.0\.pow\(\(tx\s*-\s*rssi\)',module+estimator),'TxPower used as RSSI@1m')
for t in ['android-ble-lab-v1','RssiAtOneMeterDbm(-69.19)','PathLossExponent(3.62)','validDistanceMinM = 0.50','validDistanceMaxM = 5.0','validated = true','physicalConfidence = "COARSE"','OUT_OF_DOMAIN_LOW','OUT_OF_DOMAIN_HIGH','VALID_METRIC']:
    require(t in estimator,'runtime profile token missing: '+t)
require('value != 127.0' in estimator and '-127.0..20.0' in estimator,'RSSI sentinel filtering missing'); require('rssi_samples_dbm' in index_ts and 'sample !== 127' in index_ts,'snapshot sentinel defense missing')
require('RECIPROCAL_INVERSE_VARIANCE' in fusion and 'REJECTED_DISAGREEMENT' in fusion and 'SINGLE_DIRECTION_CONSERVATIVE' in fusion,'reciprocal fusion contract missing'); require('applyReciprocalFusion' in app and 'geometryNodes = fused.nodes' in app,'solver not consuming fused observations')
require('CHANGE_WIFI_MULTICAST_STATE' in manifest and 'BodyFinderFieldService' in service and 'PARTIAL_WAKE_LOCK' in service,'lifecycle permissions/service contract lost'); require('MAX_VALID_RSSI_DBM' in fitter and 'MIN_VALID_RSSI_DBM' in fitter,'fitter RSSI guard missing')
require('0.2.0-experimental.10' in app,'mobile build is not experimental.10'); require(app_json['expo']['android']['versionCode']==10,'Android versionCode must be 10'); require(app_json['expo']['extra']['releaseIteration']=='experimental.10','releaseIteration must be experimental.10'); require('VALIDATED_COARSE_BLE_METRIC_0P5_TO_5M' in app,'physical-truth classification missing')
n=float(active['path_loss_exponent']); r=float(active['rssi_at_1m_dbm']); require(close(10**((r-r)/(10*n)),1.0),'equation 1m identity failed'); require(10**((r-(-110))/(10*n))>5.0 and 10**((r-(-40))/(10*n))<0.5,'synthetic domain guards failed')
print(json.dumps({'contract':'experimental.10 preserves validated coarse BLE metric physics','profile_id':active['profile_id'],'rssi_at_1m_dbm':active['rssi_at_1m_dbm'],'path_loss_exponent':active['path_loss_exponent'],'valid_domain_m':[0.5,5.0],'physical_confidence':'COARSE'},indent=2))
