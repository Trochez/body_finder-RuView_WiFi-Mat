#!/usr/bin/env python3
from pathlib import Path

p=Path(__file__).resolve().parents[1]/'apps/mobile/src/humanPresence.ts'
lines=p.read_text(encoding='utf-8').splitlines()
out=[]
seen_artifact=False
seen_publication=False
for line in lines:
    if line.startswith('function artifactFrom('):
        if seen_artifact:
            continue
        seen_artifact=True
    if line.startswith('function publicationFrom('):
        if seen_publication:
            continue
        seen_publication=True
    out.append(line)
text='\n'.join(out)+'\n'
if text.count('function artifactFrom(')!=1:
    raise SystemExit('artifactFrom must have exactly one implementation')
if text.count('function publicationFrom(')!=1:
    raise SystemExit('publicationFrom must have exactly one implementation')
p.write_text(text,encoding='utf-8')
print('dev20.8 humanPresence helper normalization PASS')
