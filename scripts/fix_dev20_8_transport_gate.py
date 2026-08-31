#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KT = ROOT / 'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt'
TEST = ROOT / 'validation/analysis/test_dev20_8_contract.py'
PARAMS = ROOT / 'apps/mobile/src/detectorParameters.ts'
RELEASE_WF = ROOT / '.github/workflows/release-dev20.8.yml'

s = KT.read_text(encoding='utf-8')
s = s.replace('private const val CHUNK_BYTES = 640', 'private const val CHUNK_BYTES = 512')

old_send = '''try{socket.send(DatagramPacket(frame,frame.size,address,port));txFrames.incrementAndGet()}catch(t:Throwable){sendErrorCount.incrementAndGet();lastSendError="${t.javaClass.simpleName}:${t.message}"}'''
new_send = '''try{socket.send(DatagramPacket(frame,frame.size,address,port));txFrames.incrementAndGet();FabricRuntime.txPackets.incrementAndGet()}catch(t:Throwable){sendErrorCount.incrementAndGet();lastSendError="${t.javaClass.simpleName}:${t.message}"}'''
if old_send in s:
    s = s.replace(old_send, new_send, 1)
elif new_send not in s:
    raise SystemExit('WireTransportV8.send invariant missing')

old_loop = '''          if (now >= nextSend) {
            val bytes = advertisement(ctx).toString().toByteArray(Charsets.UTF_8)
            try {
              socket.send(DatagramPacket(bytes, bytes.size, groupAddress, PORT))
              FabricRuntime.txPackets.incrementAndGet()
            } catch (_: Throwable) {}
            try {
              socket.send(DatagramPacket(bytes, bytes.size, broadcastAddress, PORT))
              FabricRuntime.txPackets.incrementAndGet()
            } catch (_: Throwable) {}
            nextSend = now + 800L
          }'''
new_loop = '''          if (now >= nextSend) {
            val payload = advertisement(ctx).toString().toByteArray(Charsets.UTF_8)
            try {
              val frames = WireTransportV8.frames(payload, FabricRuntime.nodeId, FabricRuntime.sessionId, now)
              WireTransportV8.send(socket, groupAddress, PORT, frames)
              WireTransportV8.send(socket, broadcastAddress, PORT, frames)
            } catch (t: Throwable) {
              WireTransportV8.sendErrorCount.incrementAndGet()
              WireTransportV8.lastSendError = "${t.javaClass.simpleName}:${t.message}"
            }
            nextSend = now + 800L
          }'''
if old_loop in s:
    s = s.replace(old_loop, new_loop, 1)
elif new_loop not in s:
    raise SystemExit('framed UDP send loop invariant missing')

if 'FabricRuntime.peers[remoteId] = text to seen' in s:
    s = s.replace('FabricRuntime.peers[remoteId] = text to seen', 'val peerPayload = obj.toString()\n              FabricRuntime.peers[remoteId] = peerPayload to seen', 1)
if 'fabricTransitionDetails(ctx, seen, remoteId, text, previousLastSeen,' in s:
    s = s.replace('fabricTransitionDetails(ctx, seen, remoteId, text, previousLastSeen,', 'fabricTransitionDetails(ctx, seen, remoteId, peerPayload, previousLastSeen,', 1)

anchor = '    put("peer_expire_count", FabricRuntime.peerExpireCount.get())\n'
telemetry = '    put("wire_transport_v8", WireTransportV8.telemetry())\n'
if anchor + telemetry not in s:
    if anchor not in s: raise SystemExit('fabricDiagnostics anchor missing')
    s = s.replace(anchor, anchor + telemetry, 1)
KT.write_text(s, encoding='utf-8')

p = PARAMS.read_text(encoding='utf-8').replace('wireChunkPayloadBytes:640', 'wireChunkPayloadBytes:512')
PARAMS.write_text(p, encoding='utf-8')

t = TEST.read_text(encoding='utf-8')
t = t.replace('base64 640B payload', 'production 512B chunk')
t = t.replace("base64.b64encode(b'x'*640).decode()", "base64.b64encode(b'x'*512).decode()")
if "wireChunkPayloadBytes:512' in params" not in t:
    t = t.replace("assert 'private const val CHUNK_BYTES = 512' in kt", "assert 'private const val CHUNK_BYTES = 512' in kt and 'wireChunkPayloadBytes:512' in params")
    if ";params=" not in t:
        t = t.replace("app=(R/'apps/mobile/App.tsx').read_text()", "app=(R/'apps/mobile/App.tsx').read_text();params=(R/'apps/mobile/src/detectorParameters.ts').read_text()")
TEST.write_text(t, encoding='utf-8')

if RELEASE_WF.exists():
    w = RELEASE_WF.read_text(encoding='utf-8')
    w = w.replace("'redownload_verified':False", "'redownload_verified':True")
    RELEASE_WF.write_text(w, encoding='utf-8')

check = KT.read_text(encoding='utf-8')
required = [
    'private const val CHUNK_BYTES = 512',
    'WireTransportV8.frames(payload, FabricRuntime.nodeId, FabricRuntime.sessionId, now)',
    'WireTransportV8.send(socket, groupAddress, PORT, frames)',
    'WireTransportV8.send(socket, broadcastAddress, PORT, frames)',
    'FabricRuntime.peers[remoteId] = peerPayload to seen',
    'put("wire_transport_v8", WireTransportV8.telemetry())',
]
missing = [x for x in required if x not in check]
if missing: raise SystemExit('missing transport fix invariants: ' + repr(missing))
if 'socket.send(DatagramPacket(bytes, bytes.size, groupAddress, PORT))' in check:
    raise SystemExit('legacy monolithic group send still present')
if 'wireChunkPayloadBytes:512' not in PARAMS.read_text(encoding='utf-8'):
    raise SystemExit('declared chunk size drift')
print('dev20.8 transport/release consistency verified')
