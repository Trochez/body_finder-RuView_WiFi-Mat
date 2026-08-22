#!/usr/bin/env python3
import json,sys
p=json.load(open(sys.argv[1],encoding='utf-8')); peers=(p.get('validation_run') or p).get('per_peer_at_end',(p.get('validation_run') or p).get('per_peer',[]))
for peer in peers:
    for key in ['run_callback_delta','run_valid_callback_delta','run_invalid_callback_delta','run_gap_gt_1s_delta','run_gap_gt_2s_delta','run_gap_gt_5s_delta','run_gap_gt_10s_delta','run_filtered_callback_delta','run_unfiltered_callback_delta','run_recovery_participation_count','run_first_callback_after_recovery_count']:
        if key in peer: assert peer[key]>=0,(key,peer[key])
    if (p.get('validation_run') or p).get('elapsed_ms',0)<5000: assert peer.get('run_gap_gt_5s_delta',0)<=1
print('PASS peer semantics')
