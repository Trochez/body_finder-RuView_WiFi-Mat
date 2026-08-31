#!/usr/bin/env python3
from pathlib import Path
import json,re,sys
R=Path(__file__).resolve().parents[2]
kt=(R/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt').read_text();hp=(R/'apps/mobile/src/humanPresence.ts').read_text();rs=(R/'crates/body-finder-science/src/human_detector.rs').read_text();app=(R/'apps/mobile/App.tsx').read_text()
assert 'MAX_DATAGRAM_BYTES = 1200' in kt and 'WireEnvelopeV8' in kt and 'wire_oversize_block_count' in kt and 'wire_send_error_count' in kt
assert 'val payload = advertisement(ctx).toString().toByteArray(Charsets.UTF_8)' in kt
assert 'WireTransportV8.frames(payload' in kt and 'WireTransportV8.send(socket, groupAddress' in kt and 'WireTransportV8.send(socket, broadcastAddress' in kt
assert 'FabricRuntime.peers[remoteId] = peerPayload to seen' in kt
assert 'put("wire_transport_v8", WireTransportV8.telemetry())' in kt
assert 'private const val CHUNK_BYTES = 512' in kt
assert 'socket.send(DatagramPacket(bytes, bytes.size, groupAddress, PORT))' not in kt
assert 'DecisionPublicationV8' in hp and 'decision_artifact_id' in hp and 'BodyFinderControlPlaneV8' in hp
assert 'authoritative_presence: {...localPresenceDiagnostic' not in app and "useState<string>('SMOKE_CAL_EMPTY')" in app
assert 'distributed_negative_evidence' in rs and 'HUMAN_THRESHOLD: f64 = 0.50' in rs and 'NO_HUMAN_THRESHOLD: f64 = 0.20' in rs
# hard-budget synthetic wire frames: production 512B chunk plus envelope must stay <=1200
import base64
frame={'schema':'WireEnvelopeV8','message_type':'ARTIFACT_CHUNK','session_id':'body-finder-lab','node_id':'bf-'+('a'*32),'seq':999999,'artifact_id':'adv:'+'a'*40,'artifact_sha256':'f'*64,'chunk_index':999,'chunk_count':999,'redundancy_round':2,'payload_b64':base64.b64encode(b'x'*512).decode()}
assert len(json.dumps(frame,separators=(',',':')).encode())<=1200
print('dev20.8 contract tests PASS')
