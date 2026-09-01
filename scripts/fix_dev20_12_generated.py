#!/usr/bin/env python3
from pathlib import Path

# Kotlin post-generation hardening. Keep frozen RangeFrameV9 identity explicit
# without changing the RANGE_FRAME wire message type.
p=Path('apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt')
s=p.read_text(encoding='utf-8')
if 'RANGE_FRAME_SCHEMA = "RangeFrameV9"' not in s:
    marker='private object WireTransportV10 {\n'
    if marker not in s: raise SystemExit('WireTransportV10 marker missing')
    s=s.replace(marker, marker+'  private const val RANGE_FRAME_SCHEMA = "RangeFrameV9"\n', 1)

# The generator originally matched an unqualified ConcurrentHashMap marker while
# the native source uses the fully-qualified name. Insert the V12 critical-control
# telemetry against the real generated source shape.
if 'private val criticalControlFailureCount=' not in s:
    marker='  private val oversizeControlKeyCounts=java.util.concurrent.ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong>()\n'
    if marker not in s: raise SystemExit('critical-control declaration marker missing')
    block=marker+(
        '  private val criticalControlSendAttempt=java.util.concurrent.ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong>()\n'
        '  private val criticalControlSendSuccess=java.util.concurrent.ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong>()\n'
        '  private val criticalControlSendFailure=java.util.concurrent.ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong>()\n'
        '  private val criticalControlFailureCount=java.util.concurrent.atomic.AtomicLong(0)\n'
        '  private val optionalControlDropCount=java.util.concurrent.atomic.AtomicLong(0)\n'
        '  @Volatile private var lastCriticalControlFailureKey:String?=null\n'
        '  @Volatile private var lastCriticalControlFailureSize:Long=0\n'
        '  @Volatile private var lastCriticalControlFailureError:String?=null\n'
    )
    s=s.replace(marker,block,1)

# ArtifactManifestV4 NACK backoff must be stored on the real multiline Assembly.
if 'var nackBackoffMs:Long=' not in s:
    marker='    val created:Long, val source:InetAddress, var lastNackWallMs:Long=0L,\n'
    if marker not in s: raise SystemExit('Assembly NACK marker missing')
    s=s.replace(marker,marker+'    var nackBackoffMs:Long=NACK_INTERVAL_MS,\n',1)

# Kotlin cannot smart-cast @Volatile mutable runId after a null check. Pin the
# run id once at function entry and use the immutable local for event logging.
old='fun pinDistributedStart(contextJson:String):Boolean{if(runId==null||endedWallMs!=null)return false;'
new='fun pinDistributedStart(contextJson:String):Boolean{val activeRunId=runId?:return false;if(endedWallMs!=null)return false;'
if old in s:
    s=s.replace(old,new,1)
elif new not in s:
    raise SystemExit('pinDistributedStart marker missing')
s=s.replace('ValidationEventLog.record("DISTRIBUTED_RUN_START_COMMITTED",runId,now=System.currentTimeMillis())','ValidationEventLog.record("DISTRIBUTED_RUN_START_COMMITTED",activeRunId,now=System.currentTimeMillis())',1)

old='@Synchronized fun commitDistributedFreeze(commitJson:String):Boolean{if(runId==null||endedWallMs!=null||!distributedStartCommitted)return false;'
new='@Synchronized fun commitDistributedFreeze(commitJson:String):Boolean{val activeRunId=runId?:return false;if(endedWallMs!=null||!distributedStartCommitted)return false;'
if old in s:
    s=s.replace(old,new,1)
elif new not in s:
    raise SystemExit('commitDistributedFreeze marker missing')
s=s.replace('ValidationEventLog.record("DISTRIBUTED_RUN_FREEZE_COMMITTED",runId,now=System.currentTimeMillis())','ValidationEventLog.record("DISTRIBUTED_RUN_FREEZE_COMMITTED",activeRunId,now=System.currentTimeMillis())',1)

# Assert that the generated Kotlin now contains every symbol that previously
# failed compilation, so a future generator drift fails immediately.
for required in [
    'criticalControlSendAttempt','criticalControlSendSuccess','criticalControlSendFailure',
    'criticalControlFailureCount','optionalControlDropCount','lastCriticalControlFailureKey',
    'lastCriticalControlFailureSize','lastCriticalControlFailureError','nackBackoffMs',
    'val activeRunId=runId?:return false'
]:
    if required not in s: raise SystemExit(f'Kotlin post-generation invariant missing: {required}')
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
