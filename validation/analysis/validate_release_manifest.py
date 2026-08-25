#!/usr/bin/env python3
import json,sys
m=json.load(open(sys.argv[1])); checks=[
 m.get('release')=='dev-13',
 m.get('version')=='0.2.0-experimental.13',
 m.get('report_version')==15,
 m.get('validation_snapshot_schema_version')==3,
 m.get('protocol_version')==2,
 m.get('ble_metric_rssi_at_1m_dbm')==-69.19,
 m.get('ble_metric_path_loss_exponent')==3.62,
 m.get('environment_validation_recovery_aware') is True,
 m.get('preflight_at_start_frozen') is True,
 m.get('unauthorized_strategy_detection') is True,
 m.get('human_scanning_enabled') is False,
 m.get('human_localization_validated') is False,
 m.get('rescue_use_validated') is False,
 m.get('screenshots_required_for_acceptance') is False,
 m.get('json_evidence_self_contained') is True,
]
ok=all(checks); print(json.dumps({'pass':ok,'checks':checks},indent=2)); sys.exit(0 if ok else 1)
