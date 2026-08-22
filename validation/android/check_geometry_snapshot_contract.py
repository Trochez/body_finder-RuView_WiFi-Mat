#!/usr/bin/env python3
import json, pathlib, sys
ROOT=pathlib.Path(__file__).resolve().parents[2]

src=(ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt').read_text()
for k in ['geometry_at_end','locally_computed_geometry_at_end','fused_range_observations_at_end','graph_diagnostics_at_end','reciprocal_fusion_at_end','measurement_health_at_end']:
    assert k in src,k
f=json.load(open(ROOT/'validation/fixtures/dev11/geometry-at-end-drift.json'))
assert f['completed']['geometry_at_end']['revision']==7
assert f['live_after_end']['geometry_at_end']['revision']==9
print('PASS geometry snapshot contract')
