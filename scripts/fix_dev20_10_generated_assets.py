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
print('dev20.10 generated asset hotfix applied')
