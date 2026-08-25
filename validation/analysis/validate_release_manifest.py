#!/usr/bin/env python3
import json,sys
m=json.load(open(sys.argv[1])); checks=[m.get('release')=='dev-12',m.get('version')=='0.2.0-experimental.12',m.get('protocol_version')==2,m.get('ble_metric_rssi_at_1m_dbm')==-69.19,m.get('ble_metric_path_loss_exponent')==3.62,m.get('human_scanning_enabled') is False,m.get('screenshots_required_for_acceptance') is False,m.get('json_evidence_self_contained') is True]
ok=all(checks); print(json.dumps({'pass':ok,'checks':checks},indent=2)); sys.exit(0 if ok else 1)
