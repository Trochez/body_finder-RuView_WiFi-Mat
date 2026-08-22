#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
MODULE=ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt'; POLICY=ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleContinuityPolicy.kt'; ESTIMATOR=ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleRangeEstimator.kt'; FUSION=ROOT/'apps/mobile/src/rangeFusion.ts'; GRAPH=ROOT/'apps/mobile/src/geometryDiagnostics.ts'; APP=ROOT/'apps/mobile/App.tsx'; VERSION=ROOT/'apps/mobile/src/version.ts'; APP_JSON=ROOT/'apps/mobile/app.json'; PROFILES=ROOT/'calibration/ble-range-calibration-profiles.json'; P0C=ROOT/'validation/fixtures/ble-range/p0c-calibration-summary.json'
def require(c,m):
    if not c: raise SystemExit('BLE CONTINUITY CONTRACT FAILED: '+m)
def close(a,b,t=1e-6): return abs(a-b)<=t
module=MODULE.read_text(); policy=POLICY.read_text(); estimator=ESTIMATOR.read_text(); fusion=FUSION.read_text(); graph=GRAPH.read_text(); app=APP.read_text(); version=VERSION.read_text(); app_json=json.loads(APP_JSON.read_text()); profiles=json.loads(PROFILES.read_text()); p0c=json.loads(P0C.read_text()); active=next(p for p in profiles['profiles'] if p['profile_id']==profiles['active_profile_id'])
require(active['profile_id']=='android-ble-lab-v1' and active['validated'] and active['physical_confidence']=='COARSE','profile truth changed'); require(close(float(active['rssi_at_1m_dbm']),-69.19) and close(float(active['path_loss_exponent']),3.62),'calibration changed'); require(close(float(active['valid_distance_min_m']),0.5) and close(float(active['valid_distance_max_m']),5.0),'domain changed'); require(close(float(p0c['profile']['rssi_at_1m_dbm']),-69.19),'P0c fixture changed'); require('coerceIn(0.5, 5.0)' not in estimator+module,'silent range clamp reintroduced')
for t in ['FRESH_MS = 5_000L','HOLDOVER_MAX_MS = 10_000L','HARD_EXPIRY_MS = 10_000L','SIGMA_AGING_M_PER_S = 0.15','BleRangeTemporalState.HOLDOVER','BleRangeTemporalState.EXPIRED','holdoverEligible','agedSigma']:
    require(t in policy,'temporal policy token missing: '+t)
validator_pos=module.find('BleRangeEstimator.isValidBleRssi(result.rssi.toDouble())'); queue_pos=module.find('queue.addLast(RssiSample(result.rssi, advertisedTx, now))'); require(validator_pos>=0 and queue_pos>=0 and validator_pos<queue_pos,'RSSI validation is not pre-queue')
for t in ['invalidRssiEventsByIdentity','invalidRssiTotalCount','latest_invalid_rssi_dbm','median_valid_rssi_dbm','raw_sample_count_5s','valid_rssi_sample_count_5s','invalid_rssi_sample_count_5s','raw_sample_count_8s','valid_rssi_sample_count_8s','invalid_rssi_sample_count_8s','lastValidRangeByPeer','LastValidRangeState','LAST_VALID_HOLDOVER','BleContinuityPolicy.agedSigma','bodyFinderCohortHealth','BF_COHORT_STALLED','peer_gap_state','PEER_TEMPORARILY_NOT_OBSERVED']:
    require(t in module+policy,'continuity token missing: '+t)
require('FabricRuntime.lastValidRangeByPeer.remove(nodeId)' in module,'peer expiry does not invalidate cached range')
for t in ['range_temporal_state','HOLDOVER_MAX_MS = 10_000','source_temporal_states','oldest_source_age_ms','REJECTED_DISAGREEMENT','RECIPROCAL_INVERSE_VARIANCE','SINGLE_DIRECTION_CONSERVATIVE']:
    require(t in fusion,'fusion temporal contract missing: '+t)
for t in ['fresh_metric_edge_count','holdover_metric_edge_count','oldest_metric_edge_age_ms','geometry_temporal_quality','HOLDOVER_DOMINANT','MIXED_FRESH_HOLDOVER']:
    require(t in graph,'geometry temporal diagnostic missing: '+t)
require("reciprocalState !== 'REJECT'" in graph and "temporalState === 'FRESH' || temporalState === 'HOLDOVER'" in graph,'graph truth gate missing')
for t in ['fresh_metric_range_uptime_percent','usable_metric_range_uptime_percent','holdover_metric_uptime_percent','snapshot_frozen','snapshot_schema_version']:
    require(t in module,'validation-run metric missing: '+t)
require('export_auto_finalized_validation_run' in app and 'BodyFinderNative.endValidationRun()' in app,'share auto-finalization contract missing'); require('0.2.0-experimental.11' in version and 'reportVersion: 13' in version,'mobile build is not experimental.11'); require(app_json['expo']['android']['versionCode']==11 and app_json['expo']['extra']['releaseIteration']=='experimental.11','Android release metadata wrong'); require('humanScanningEnabled: false' in version,'human scanning must remain blocked')
print(json.dumps({'contract':'experimental.11 preserves bounded BLE metric continuity','profile_id':'android-ble-lab-v1','fresh_ms':5000,'holdover_max_ms':10000,'hard_expiry_ms':10000,'sigma_aging_m_per_s':0.15,'human_scanning_enabled':False},indent=2))
