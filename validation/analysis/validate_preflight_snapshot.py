#!/usr/bin/env python3
import json,sys
p=sys.argv[1]; d=json.load(open(p)); r=d.get('validation_run',d); q=r.get('preflight_at_start') or {}
checks={
 'ready':q.get('ready') is True,
 'bluetooth_on':q.get('bluetooth_on') is True,
 'ble_permissions_ready':q.get('ble_permissions_ready') is True,
 'battery_saver_off':q.get('battery_saver_off') is True,
 'screen_on':q.get('screen_on') is True,
 'app_foreground':q.get('app_foreground') is True,
 'foreground_service_running':q.get('foreground_service_running') is True,
 'ble_scanner_running':q.get('ble_scanner_running') is True,
 'expected_ble_peer_count>=2':q.get('expected_ble_peer_count',0)>=2,
 'strategy_primary':q.get('acquisition_strategy')=='FILTERED_PRIMARY',
 'filter_mode':q.get('filter_mode')=='MANUFACTURER_FILTERED',
 'hardware_filter_count>0':q.get('hardware_filter_count',0)>0,
 'blocking_reasons_empty':not q.get('blocking_reasons'),
}
ok=all(checks.values()); print(json.dumps({'file':p,'checks':checks,'pass':ok},indent=2)); sys.exit(0 if ok else 1)
