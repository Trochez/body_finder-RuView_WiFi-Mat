#!/usr/bin/env python3
from pathlib import Path
r=Path(__file__).resolve().parents[2]; a=(r/'apps/mobile/App.tsx').read_text(); v=(r/'apps/mobile/src/version.ts').read_text(); n=(r/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt').read_text()
assert '0.2.0-experimental.12' in v and 'manufacturer-filtered LOW_LATENCY scanning as FILTERED_PRIMARY' in a
assert 'low-latency ALL_MATCHES scanning with Body Finder manufacturer/payload validation' not in a
for t in ['logical_acquisition_strategy','filter_configuration','MANUFACTURER_FILTERED','scan_generation']: assert t in n,t
assert 'VALIDATION_ENVVIRONMENT_INVALID' not in a
print('acquisition truth contract: PASS')
