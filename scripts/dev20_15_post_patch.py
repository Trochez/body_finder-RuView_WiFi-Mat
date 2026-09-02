#!/usr/bin/env python3
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'apps/mobile/src/humanPresence.ts'
s=p.read_text()
old="{schema:'CalibrationAckWireV2',s,n:localNodeId"
new="{schema:'CalibrationAckWireV2',s:sid,n:localNodeId"
if old not in s and new not in s:
    raise SystemExit('CalibrationAckWireV2 anchor not found')
if old in s:
    p.write_text(s.replace(old,new))
print('dev20.15 post-patch PASS')
