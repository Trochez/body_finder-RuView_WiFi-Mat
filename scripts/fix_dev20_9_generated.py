#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
smoke = root / 'validation/analysis/validate_dev20_9_smoke.py'
s = smoke.read_text()
s = s.replace(")]]\n  expected=", ")]\n  expected=")
smoke.write_text(s)

# Fail early if the generator accidentally retains the known malformed sequence.
assert ")]]\n  expected=" not in s
print('dev20.9 generated normalization: PASS')
