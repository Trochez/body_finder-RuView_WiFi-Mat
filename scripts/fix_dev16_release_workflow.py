#!/usr/bin/env python3
from pathlib import Path
p=Path('.github/workflows/release-exp16.yml')
s=p.read_text()
old="gh release create dev-16 dist/* --prerelease"
new="gh release create dev-16 $(find dist -maxdepth 1 -type f -print | sort) --prerelease"
if s.count(old)!=1:
    raise SystemExit(f'expected exactly one release glob, got {s.count(old)}')
p.write_text(s.replace(old,new,1))
print('DEV16_RELEASE_WORKFLOW_FIXED')
