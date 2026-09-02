#!/usr/bin/env python3
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'apps/mobile/src/humanPresence.ts'
s=p.read_text()
replacements=[
("function calibrationAckWire(localNodeId:string,sid:string,topology_hash:string)","function calibrationAckWire(localNodeId:string|null,sid:string,topology_hash:string)"),
("{schema:'CalibrationAckWireV2',s,n:localNodeId","{schema:'CalibrationAckWireV2',s:sid,n:localNodeId"),
("artifacts.push({artifact_id:cm.artifact_id,artifact_type:'CALIBRATION_FINAL_V10'","artifacts.push({artifact_id:cm.a,artifact_type:'CALIBRATION_FINAL_V10'")]
changed=False
for old,new in replacements:
    if old in s:
        s=s.replace(old,new);changed=True
    elif new not in s:
        raise SystemExit(f'anchor not found: {old}')
if changed:p.write_text(s)
print('dev20.15 post-patch PASS')
