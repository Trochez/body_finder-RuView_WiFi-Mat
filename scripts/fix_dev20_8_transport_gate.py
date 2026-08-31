#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KT = ROOT / 'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt'
TEST = ROOT / 'validation/analysis/test_dev20_8_contract.py'

s = KT.read_text(encoding='utf-8')

# Keep enough headroom for long node/session/sequence/artifact identifiers. 512 raw bytes
# base64-encode to 684 bytes and keep the complete JSON envelope comfortably <1200 B.
s = s.replace('private const val CHUNK_BYTES = 640', 'private const val CHUNK_BYTES = 512')

old_send = '''try{socket.send(DatagramPacket(frame,frame.size,address,port));txFrames.incrementAndGet()}catch(t:Throwable){sendErrorCount.incrementAndGet();lastSendError="${t.javaClass.simpleName}:${t.message}"}'''
new_send = '''try{socket.send(DatagramPacket(frame,frame.size,address,port));txFrames.incrementAndGet();FabricRuntime.txPackets.incrementAndGet()}catch(t:Throwable){sendErrorCount.incrementAndGet();lastSendError="${t.javaClass.simpleName}:${t.message}"}'''
if old_send not in s:
    raise SystemExit('WireTransportV8.send anchor missing')
s = s.replace(old_send, new_send, 1)

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
if old_loop not in s:
    raise SystemExit('monolithic UDP send loop anchor missing')
s = s.replace(old_loop, new_loop, 1)

# After a chunked artifact completes, peer state must store the reconstructed advertisement,
# never the final ARTIFACT_CHUNK envelope that happened to complete reassembly.
s = s.replace('FabricRuntime.peers[remoteId] = text to seen', 'val peerPayload = obj.toString()\n              FabricRuntime.peers[remoteId] = peerPayload to seen', 1)
s = s.replace('fabricTransitionDetails(ctx, seen, remoteId, text, previousLastSeen,', 'fabricTransitionDetails(ctx, seen, remoteId, peerPayload, previousLastSeen,', 1)

# Make wire telemetry directly available in the diagnostic/export plane, not only inside the
# transferred advertisement artifact.
anchor = '    put("peer_expire_count", FabricRuntime.peerExpireCount.get())\n'
if anchor not in s:
    raise SystemExit('fabricDiagnostics anchor missing')
s = s.replace(anchor, anchor + '    put("wire_transport_v8", WireTransportV8.telemetry())\n', 1)

KT.write_text(s, encoding='utf-8')

t = TEST.read_text(encoding='utf-8')
t = t.replace('# hard-budget synthetic wire frames: base64 640B payload plus envelope must stay <=1200', '# hard-budget synthetic wire frames: production 512B chunk plus envelope must stay <=1200')
t = t.replace("base64.b64encode(b'x'*640).decode()", "base64.b64encode(b'x'*512).decode()")
t = t.replace("assert 'socket.send(DatagramPacket(payload, payload.size' not in kt", "assert 'val payload = advertisement(ctx).toString().toByteArray(Charsets.UTF_8)' in kt\nassert 'WireTransportV8.frames(payload' in kt and 'WireTransportV8.send(socket, groupAddress' in kt and 'WireTransportV8.send(socket, broadcastAddress' in kt\nassert 'FabricRuntime.peers[remoteId] = peerPayload to seen' in kt\nassert 'put(\"wire_transport_v8\", WireTransportV8.telemetry())' in kt\nassert 'private const val CHUNK_BYTES = 512' in kt\nassert 'socket.send(DatagramPacket(bytes, bytes.size, groupAddress, PORT))' not in kt")
TEST.write_text(t, encoding='utf-8')

# Hard self-checks before CI compilers run.
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
if missing:
    raise SystemExit('missing transport fix invariants: ' + repr(missing))
if 'socket.send(DatagramPacket(bytes, bytes.size, groupAddress, PORT))' in check:
    raise SystemExit('legacy monolithic group send still present')
print('dev20.8 transport gate fix applied')
