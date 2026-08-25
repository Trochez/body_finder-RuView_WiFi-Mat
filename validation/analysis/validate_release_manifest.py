#!/usr/bin/env python3
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]); m=json.load(open(p)); errs=[]
if m.get('release')=='dev-14':
 expected={'version':'0.2.0-experimental.14','protocol_version':2,'validation_snapshot_schema_version':3,'json_evidence_self_contained':True,'screenshots_required_for_acceptance':False,'ble_metric_profile':'android-ble-lab-v1','ble_metric_min_samples':3,'ble_fresh_ms':5000,'ble_holdover_max_ms':10000,'ble_hard_expiry_ms':10000,'ble_recovery_unfiltered_window_ms':10000,'ble_filtered_recovery_probe_ms':15000,'ble_filtered_recovery_probe_exit_target_ms':14500,'ble_restart_cooldown_ms':30000,'ble_max_recovery_attempts_per_5min':3,'automatic_geometry':True,'manual_node_coordinates_required':False,'human_scanning_enabled':False,'human_localization_validated':False,'rescue_use_validated':False}
 for k,v in expected.items():
  if m.get(k)!=v: errs.append(f'{k}: expected {v!r}, got {m.get(k)!r}')
arts=m.get('artifacts',[])
if arts and len({a.get('name') for a in arts})!=len(arts): errs.append('duplicate artifact names')
print(json.dumps({'pass':not errs,'errors':errs},indent=2)); sys.exit(0 if not errs else 1)
