#!/usr/bin/env python3
from pathlib import Path

p = Path(__file__).with_name('apply_dev20_7_delta.py')
src = p.read_text(encoding='utf-8')
for field in (
    'persistence_score',
    'segmented_transition_score',
    'percentile_spread_change_score',
    'burst_activity_score',
    'quality',
):
    src = src.replace(f'pub {field}: f64;', f'pub {field}: f64,')
# The dev20.6 report rounds baseline support to 0.333333; the detector computes
# the exact 1/3 ratio. Keep the production gate exact and fix only the fixture.
src = src.replace(
    "0.333333 >= (1.0/3.0)",
    "(1.0/3.0) >= (1.0/3.0)",
)
exec(compile(src, str(p), 'exec'), {'__name__': '__main__', '__file__': str(p)})
