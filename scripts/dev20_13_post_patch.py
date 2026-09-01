#!/usr/bin/env python3
from pathlib import Path
R=Path('.')

def patch(path, old, new, required=True):
    p=R/path
    s=p.read_text(encoding='utf-8')
    if old in s:
        s=s.replace(old,new)
        p.write_text(s,encoding='utf-8')
        return True
    if required and new not in s:
        raise SystemExit(f'PATCH_MISSING {path}: {old}')
    return False

# Native transport object is WireTransportV10; telemetry schema is V13 but the object name remains wire-compatible V10.
patch('apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt',
      'WireTransport.telemetry()', 'WireTransportV10.telemetry()')
patch('apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt',
      '.put("snapshot_schema_version", 15)', '.put("snapshot_schema_version", 16)', required=False)

# Keep the implementation generator itself correct for future reproductions.
patch('scripts/implement_dev20_13.py','WireTransport.telemetry()','WireTransportV10.telemetry()',required=False)
patch('scripts/implement_dev20_13.py',"s=s.replace('snapshot_schema_version\\\", 15','snapshot_schema_version\\\", 16')",
      "s=s.replace('snapshot_schema_version\\\", 15','snapshot_schema_version\\\", 16').replace('.put(\\\"snapshot_schema_version\\\", 15)','.put(\\\"snapshot_schema_version\\\", 16)')",required=False)

# Release runs only from the already gated/committed source tree. Re-running the implementation generator in release
# would be both unnecessary and a source of non-idempotent mutation.
p=R/'.github/workflows/release-dev20.13.yml'
if p.exists():
    s=p.read_text(encoding='utf-8')
    s=s.replace('      - name: Apply dev20.13 implementation\n        run: python3 scripts/implement_dev20_13.py\n','')
    s=s.replace('      - name: Apply dev20.13 implementation\n        run: |\n          python3 scripts/implement_dev20_13.py\n','')
    p.write_text(s,encoding='utf-8')

# Make the branch copy of the engineering workflow truthful/usable too.
p=R/'.github/workflows/dev20.13-engineering.yml'
if p.exists():
    s=p.read_text(encoding='utf-8')
    s=s.replace('run: python3 scripts/implement_dev20_13.py','run: |\n          python3 scripts/implement_dev20_13.py\n          python3 scripts/dev20_13_post_patch.py')
    s=s.replace('grep -q "PRE_RUN_DIAGNOSTIC_V1" apps/mobile/App.tsx','grep -q "exportPreRunDiagnosticJson" apps/mobile/App.tsx\n          grep -q "PRE_RUN_DIAGNOSTIC_V1" apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt')
    p.write_text(s,encoding='utf-8')

print('DEV20_13_POST_PATCH_APPLIED')
