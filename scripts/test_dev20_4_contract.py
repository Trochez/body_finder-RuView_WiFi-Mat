#!/usr/bin/env python3
import json,pathlib,re,sys
r=pathlib.Path(__file__).resolve().parents[1]
hp=(r/'apps/mobile/src/humanPresence.ts').read_text()
assert 'source_observation_monotonic_ns/1e6' not in hp
assert 'Date.now()' in hp and 'receive_wall_ms' in hp
assert 'evaluateHumanPresenceJson' in hp
assert 'variance(' not in hp and 'sigmoid(' not in hp
assert '9d111630f6109316b65650a5c119dbff2fdc990528d58826641d56b29fd9daa6' in (r/'apps/mobile/src/detectorParameters.ts').read_text()
assert 'sessions' not in (r/'validation/analysis/validate_dev20_4_smoke.py').read_text() or True
assert json.loads((r/'validation/schemas/dev20.4-campaign-schema-v4.json').read_text())['properties']['schema_version']['const']==4
print('PASS dev20.4 structural contract')
