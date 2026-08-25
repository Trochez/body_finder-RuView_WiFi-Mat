#!/usr/bin/env python3
import json,sys
m=json.load(open(sys.argv[1])); assert m['release']=='dev-12'; assert m['version']=='0.2.0-experimental.12'; assert m['protocol_version']==2; assert m['ble_metric_rssi_at_1m_dbm']==-69.19; assert m['ble_metric_path_loss_exponent']==3.62; assert m['human_scanning_enabled'] is False; assert m['human_localization_validated'] is False; assert m['rescue_use_validated'] is False; print('PASS dev12 release manifest')
