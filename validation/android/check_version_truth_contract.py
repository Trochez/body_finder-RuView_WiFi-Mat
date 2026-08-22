#!/usr/bin/env python3
import json, pathlib, sys
ROOT=pathlib.Path(__file__).resolve().parents[2]

app=(ROOT/'apps/mobile/App.tsx').read_text(); v=(ROOT/'apps/mobile/src/version.ts').read_text(); cfg=json.load(open(ROOT/'apps/mobile/app.json'))['expo']
assert "0.2.0-experimental.11" in v
assert 'reportVersion: 13' in v
assert cfg['android']['versionCode']==11
assert cfg['extra']['releaseIteration']=='experimental.11'
for stale in ['experimental.9','experimental.10']:
    assert stale not in app, stale
assert 'HUMAN_SCANNING_ENABLED' in app
print('PASS version truth contract')
