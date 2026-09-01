#!/usr/bin/env python3
import pathlib,json
R=pathlib.Path(__file__).resolve().parents[2]
def text(p):return(R/p).read_text()
assert '0.2.0-experimental.20.13' in text('apps/mobile/src/version.ts')
assert 'reportVersion: 33' in text('apps/mobile/src/version.ts') and 'versionCode: 33' in text('apps/mobile/src/version.ts') and 'snapshotSchemaVersion: 16' in text('apps/mobile/src/version.ts')
assert 'deterministic-multinode-rssi-fusion-v9' in text('crates/body-finder-science/src/human_detector.rs')
assert 'f5795d40fbfb1de728b8576e214b249ada67f70d7962e1bf7794eb9c7d251f17' in text('apps/mobile/src/detectorParameters.ts')
assert 'RangeFrameV9' in text('apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt')
assert 'GeometryPublicationV11' in text('apps/mobile/src/autogeometry.ts')
assert 'manual_geometry_override: false' in text('apps/mobile/App.tsx')
assert 'WireTransportTelemetryV13' in text('apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt')
assert 'Function("exportPreRunDiagnosticJson")' in text('apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt')
print(json.dumps({'schema':'dev20.13-contract-report-v1','status':'PASS'}))
