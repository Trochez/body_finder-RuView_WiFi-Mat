#!/usr/bin/env python3
from pathlib import Path
import re
R=Path(__file__).resolve().parents[1]
# Repair accidental literal newline embedded between Python quote delimiters in generated validators.
for rel in ['validation/analysis/validate_dev20_10_smoke.py','validation/analysis/validate_dev20_10_campaign.py']:
    p=R/rel
    s=p.read_text()
    s=re.sub(r"write_text\(json\.dumps\(o,indent=2\)\+'\s*'\)", "write_text(json.dumps(o,indent=2))", s)
    p.write_text(s)
# Legacy APK lives outside apps/mobile; keep its version identity aligned.
legacy=R/'apps/android-legacy/app/build.gradle'
if legacy.exists():
    s=legacy.read_text()
    s=re.sub(r'versionCode\s+29\b','versionCode 30',s)
    s=s.replace('0.2.0-experimental.20.9-legacy','0.2.0-experimental.20.10-legacy')
    s=s.replace('0.2.0-experimental.20.9','0.2.0-experimental.20.10')
    legacy.write_text(s)
# The dev20.10 applicator changes ValidationRuntime.start to require scenarioId.
# Patch the pre-existing multiline bridge call so Android compilation receives it atomically.
native=R/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt'
if native.exists():
    s=native.read_text()
    old='''        FabricRuntime.rxPackets.get(),\n        preflight.toString(),\n      )'''
    new='''        FabricRuntime.rxPackets.get(),\n        preflight.toString(),\n        scenario,\n      )'''
    if old in s:
        s=s.replace(old,new,1)
    elif new not in s:
        raise SystemExit('missing multiline ValidationRuntime.start bridge anchor')
    native.write_text(s)
print('dev20.10 generated asset hotfix applied')
