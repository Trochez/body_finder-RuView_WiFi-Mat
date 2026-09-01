#!/usr/bin/env python3
from pathlib import Path

# Kotlin: keep frozen RangeFrameV9 identity explicit without changing RANGE_FRAME wire type.
p=Path('apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt')
s=p.read_text(encoding='utf-8')
if 'RANGE_FRAME_SCHEMA = "RangeFrameV9"' not in s:
    marker='private object WireTransportV10 {\n'
    if marker not in s: raise SystemExit('WireTransportV10 marker missing')
    s=s.replace(marker, marker+'  private const val RANGE_FRAME_SCHEMA = "RangeFrameV9"\n', 1)
p.write_text(s,encoding='utf-8')

# TypeScript: after the durable-ledger fast path returns for every cached decision,
# the final fallback can only represent "no cached decision". Do not reference a
# value TypeScript has correctly narrowed to undefined/never there.
p=Path('apps/mobile/src/humanPresence.ts')
s=p.read_text(encoding='utf-8')
old="return fallback(cal.state==='STALE_AUTHORITY'?cal.reason:'WAIT_DECISION_EXPIRED',cal.state,{decision_freshness_state:cached?'EXPIRED':'WAIT_DECISION',last_valid_decision_sequence:cached?.sequence??null,last_valid_decision_digest:cached?.decision.canonical_digest??null,transport_liveness_state:transportStates(nodes)})"
new="return fallback(cal.state==='STALE_AUTHORITY'?cal.reason:'WAIT_DECISION_EXPIRED',cal.state,{decision_freshness_state:'WAIT_DECISION',last_valid_decision_sequence:null,last_valid_decision_digest:null,transport_liveness_state:transportStates(nodes)})"
if old in s:
    s=s.replace(old,new,1)
elif new not in s:
    raise SystemExit('humanPresence durable fallback marker missing')
p.write_text(s,encoding='utf-8')
print('dev20.12 generated fixes applied')
