#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PARAMS=ROOT/'apps/mobile/src/detectorParameters.ts'
KT=ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt'
HP=ROOT/'apps/mobile/src/humanPresence.ts'

p=PARAMS.read_text(encoding='utf-8').replace('wireChunkPayloadBytes:640','wireChunkPayloadBytes:512')
PARAMS.write_text(p,encoding='utf-8')

kt=KT.read_text(encoding='utf-8'); hp=HP.read_text(encoding='utf-8'); params=PARAMS.read_text(encoding='utf-8')
required_kt=[
 'MAX_DATAGRAM_BYTES = 1200','CHUNK_BYTES = 512','ARTIFACT_ACK','ARTIFACT_NACK','RANGE_FRAME','CONTROL_FRAME',
 'GEOMETRY_FRAME','artifactRetransmitChunks','artifactCacheEvictions','artifactReassemblyTimeouts','wire_payload_bytes',
 'tx_frames_by_type','rx_frames_by_type','WireTransportV8.maintenance(now)','WireTransportV8.noteReceiveError(t)'
]
missing=[x for x in required_kt if x not in kt]
if missing: raise SystemExit('native reliable-wire invariants missing: '+repr(missing))
if 'REDUNDANCY_ROUNDS' in kt: raise SystemExit('blind redundancy still present')
if 'socket.send(DatagramPacket(bytes, bytes.size, groupAddress, PORT))' in kt: raise SystemExit('legacy monolithic UDP send remains')
required_hp=['CalibrationPublicationV8','CalibrationAckV8','DecisionPublicationV8','DecisionAckV8','artifact_payloads_v1','DECISION_ARTIFACT_V8_PENDING','decision_control_plane_v8_artifact_complete']
missing=[x for x in required_hp if x not in hp]
if missing: raise SystemExit('control/artifact plane invariants missing: '+repr(missing))
if 'decision_artifact:cached.decision' in hp: raise SystemExit('decision artifact still inline')
if 'artifact:cal.artifact' in hp: raise SystemExit('calibration artifact still inline')
if 'wireChunkPayloadBytes:512' not in params or 'wireMaxDatagramBytes:1200' not in params: raise SystemExit('declared MTU/chunk drift')
print('dev20.8 final consistency PASS')
