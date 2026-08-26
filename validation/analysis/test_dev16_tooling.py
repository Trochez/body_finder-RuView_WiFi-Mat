#!/usr/bin/env python3
import sys
sys.path.insert(0,'validation/analysis')
from dev16_validation import UNFILTERED_TARGET,UNFILTERED_HARD,PROBE_TARGET,PROBE_HARD,ROLLING_LIMIT
assert (UNFILTERED_TARGET,UNFILTERED_HARD)==(9500,10000)
assert (PROBE_TARGET,PROBE_HARD)==(14500,15000)
assert ROLLING_LIMIT==3
for d,fail,warn in [(9499,False,False),(9500,False,False),(9501,False,True),(9999,False,True),(10000,False,True),(10001,True,False),(10148,True,False)]:
    assert (d>UNFILTERED_HARD)==fail and ((UNFILTERED_TARGET<d<=UNFILTERED_HARD)==warn)
for d,fail,warn in [(14500,False,False),(14501,False,True),(14999,False,True),(15000,False,True),(15001,True,False)]:
    assert (d>PROBE_HARD)==fail and ((PROBE_TARGET<d<=PROBE_HARD)==warn)
print('DEV16_TOOLING_BOUNDARIES_PASS')
