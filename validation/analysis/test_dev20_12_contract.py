#!/usr/bin/env python3
import json,pathlib,subprocess,sys,tempfile
ROOT=pathlib.Path(__file__).resolve().parents[2]
assert '0.2.0-experimental.20.12' in (ROOT/'apps/mobile/src/version.ts').read_text()
for p in ['control-plane-v10-schema.json','run-start-v1-schema.json','snapshot-freeze-v2-schema.json','artifact-manifest-v4-schema.json','wire-transport-telemetry-v12-schema.json','dev20.12-evidence-schema-v15.json']:json.loads((ROOT/'validation/schemas'/p).read_text())
subprocess.run([sys.executable,str(ROOT/'validation/analysis/test_dev20_12_multi_runtime.py')],check=True)
kt=(ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt').read_text();assert 'COMPACT_CONTROL_PAYLOAD_TARGET_BYTES = 600' in kt and 'ArtifactManifestV4' in kt and 'WireTransportTelemetryV12' in kt and 'criticalControlFailureCount' in kt
app=(ROOT/'apps/mobile/App.tsx').read_text();assert 'startDistributedValidationRun' in app and 'commitDistributedFreezeAndEnd' in app
print('dev20.12 contract PASS')
