#!/usr/bin/env python3
import json, pathlib, sys
ROOT=pathlib.Path(__file__).resolve().parents[2]

p=json.load(open(ROOT/'validation/fixtures/dev11/peer-lifetime-vs-run-scope.json'))['peer']
assert p['lifetime_gap_gt_5s_count']>p['run_gap_gt_5s_delta']
assert p['peer_recovery_count']==p['run_recovery_participation_count']
src=(ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleAcquisitionPolicy.kt').read_text()
assert 'peerRecoveryCount.incrementAndGet()' not in src
for k in ['lifetime_callback_count','run_filtered_callback_delta','run_unfiltered_callback_delta','run_recovery_participation_count','run_first_callback_after_recovery_count','last_recovery_generation_seen','last_recovery_callback_latency_ms']:
    assert k in src,k
print('PASS peer telemetry semantics')
