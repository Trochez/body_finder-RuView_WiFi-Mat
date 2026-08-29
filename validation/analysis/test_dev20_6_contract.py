#!/usr/bin/env python3
from pathlib import Path
import json
R=Path(__file__).resolve().parents[2]
checks={'build':('apps/mobile/src/version.ts','0.2.0-experimental.20.6'),'rust':('crates/body-finder-science/src/human_detector.rs','deterministic-multinode-rssi-fusion-v6'),'hash':('crates/body-finder-science/src/human_detector.rs','0fdb8a3b9ae003cc6d138c970ecdc0237bc2186b440e5469763e2d6c2e49f2f1'),'pub':('apps/mobile/src/humanPresence.ts','CalibrationPublicationV6'),'ack':('apps/mobile/src/humanPresence.ts','CalibrationAckV6'),'membership':('apps/mobile/src/humanPresence.ts','transport_liveness_state'),'native':('apps/mobile/modules/body-finder-native/index.ts','updateControlPlaneJson'),'schema':('apps/mobile/modules/body-finder-native/index.ts','dev20.6-self-contained-json-evidence-v9'),'digest':('apps/mobile/modules/body-finder-native/index.ts','snapshot_consistency_digest')}
bad=[k for k,(p,n) in checks.items() if n not in (R/p).read_text()]
if bad: raise SystemExit('contract checks failed: '+','.join(bad))
m=json.loads((R/'validation/fixtures/dev20_6/detector-parameter-manifest-v6.json').read_text()); assert m['detector_parameter_hash']=='0fdb8a3b9ae003cc6d138c970ecdc0237bc2186b440e5469763e2d6c2e49f2f1'
print('dev20.6 contract checks PASS')
