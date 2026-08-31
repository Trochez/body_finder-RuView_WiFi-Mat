#!/usr/bin/env python3
import json,pathlib,re
R=pathlib.Path(__file__).resolve().parents[2]
f=json.loads((R/'validation/fixtures/dev20_9/pixel-7-pro-no-run-long-1.regression.json').read_text())
assert f['active_udp_peers']==2 and f['healthy_ble_peers']==2 and f['fresh_metric_ranges']==2
assert f['geometry_state']=='GEOMETRY_STALE' and f['positions']==[]
assert 'implausibly ahead' in f['rejected_reason'] and f['max_datagram_bytes_observed']>1200 and f['wire_oversize_block_count']>0
assert f['stale_old_node_id']!=f['current_node_id'] and f['peer_has_published_geometry'] and f['local_published_geometry'] is None
geo=(R/'apps/mobile/src/autogeometry.ts').read_text(); native=(R/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt').read_text(); version=(R/'apps/mobile/src/version.ts').read_text(); smoke=(R/'validation/analysis/validate_dev20_9_smoke.py').read_text()
assert 'implausibly ahead of its observer' not in geo
assert 'effective_age_ms' in geo and 'sender_range_age_ms' in geo
assert 'WireEnvelopeV9' in native and 'RANGE_FRAME_TARGET_BYTES = 1050' in native and 'required_frame_oversize_count' in native
assert 'source_detail' not in re.search(r'for\(i in 0 until ranges.length\(\)\).*?val cp=',native,re.S).group(0)
assert 'instanceEpoch' in native and 'GeometryPublicationV9' in native
assert "0.2.0-experimental.20.9" in version and 'snapshotSchemaVersion: 12' in version
assert "'g10_go':not fails" in smoke and "'final_go':False" in smoke
print('dev20.9 contract regression: PASS')
