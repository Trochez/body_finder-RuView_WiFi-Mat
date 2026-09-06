#!/usr/bin/env python3
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]

def replace_once(path: str, old: str, new: str) -> None:
    p = ROOT / path
    text = p.read_text(encoding='utf-8')
    if new in text and old not in text:
        return
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{path}: expected one baseline pattern, found {count}: {old[:120]!r}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')

# Keep npm package metadata aligned with the release identity.
for path in ['apps/mobile/package.json', 'apps/mobile/package-lock.json']:
    p = ROOT / path
    text = p.read_text(encoding='utf-8')
    text = text.replace('0.2.0-experimental.20.17', '0.2.0-experimental.20.18')
    p.write_text(text, encoding='utf-8')

# The native transport injects artifact_sha256 only when the control DTO carries
# calibration_artifact_id / decision_artifact_id. dev20.18 omitted the calibration
# reference, so receiver-local verified promotion could never obtain the advertised SHA.
replace_once(
    'apps/mobile/src/humanPresence.ts',
    "artifact_id:`calibration:${raw.i}`,artifact_sha256:String(raw.artifact_sha256??''),",
    "artifact_id:String(raw.calibration_artifact_id??`calibration:${raw.i}`),artifact_sha256:String(raw.artifact_sha256??''),",
)
replace_once(
    'apps/mobile/src/humanPresence.ts',
    "i:cal.artifact.calibration_id,h:cal.artifact.calibration_hash,t:topology_hash,",
    "i:cal.artifact.calibration_id,calibration_artifact_id:`calibration:${cal.artifact.calibration_id}`,h:cal.artifact.calibration_hash,t:topology_hash,",
)

# Remove ignored duplicate root-level Expo metadata. The authoritative values already
# live under the expo object.
p = ROOT / 'apps/mobile/app.json'
d = json.loads(p.read_text(encoding='utf-8'))
d.pop('version', None)
d.pop('android', None)
p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

print('DEV20_18_RUNTIME_HOTFIX_PATCH=APPLIED')
