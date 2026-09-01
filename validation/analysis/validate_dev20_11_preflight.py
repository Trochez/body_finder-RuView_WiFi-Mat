#!/usr/bin/env python3
import argparse,json,pathlib,sys
p=argparse.ArgumentParser();p.add_argument('--diagnostics',required=True);p.add_argument('--output',default='dev20.11-preflight.json');a=p.parse_args();d=json.loads(pathlib.Path(a.diagnostics).read_text());cp=d.get('control_plane') or d.get('local',{}).get('control_plane') or {};fail=[]
if not (cp.get('scenario_command_v1') or {}).get('command_digest'):fail.append('SCENARIO_COMMAND_MISSING')
if d.get('manual_geometry_override') is True:fail.append('MANUAL_GEOMETRY_FORBIDDEN')
if int(d.get('ble_peer_count') or d.get('active_ble_peer_count') or 0)!=2:fail.append('EXACTLY_2_REMOTE_BLE_PEERS_REQUIRED')
o={'schema':'Dev20.11PreflightV1','ready':not fail,'failures':fail,'screenshots_required':False};pathlib.Path(a.output).write_text(json.dumps(o,indent=2)+'\n');print(json.dumps(o,indent=2));sys.exit(0 if not fail else 2)
