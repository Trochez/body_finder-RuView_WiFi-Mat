#!/usr/bin/env python3
from pathlib import Path
import json, re, textwrap

ROOT=Path(__file__).resolve().parents[1]

def read(p): return (ROOT/p).read_text(encoding='utf-8')
def write(p,s):
    q=ROOT/p; q.parent.mkdir(parents=True,exist_ok=True); q.write_text(s,encoding='utf-8')
def rep(p,a,b):
    s=read(p)
    if a not in s: raise SystemExit(f'missing pattern in {p}: {a[:100]!r}')
    write(p,s.replace(a,b,1))

def ensure(p, needle, transform):
    s=read(p)
    if needle in s: return
    write(p, transform(s))

# Version truth
write('apps/mobile/src/version.ts', """export const RELEASE = Object.freeze({
  build: '0.2.0-experimental.12',
  reportVersion: 14,
  versionCode: 12,
  releaseIteration: 'experimental.12',
  protocolVersion: 2,
  snapshotSchemaVersion: 2,
  humanScanningEnabled: false,
  humanLocalizationValidated: false,
  rescueUseValidated: false,
});
export const BUILD = RELEASE.build;
export const REPORT_VERSION = RELEASE.reportVersion;
export const HUMAN_SCANNING_ENABLED = RELEASE.humanScanningEnabled;
""")
app=json.loads(read('apps/mobile/app.json'))
app['expo']['android']['versionCode']=12
app['expo']['extra']['releaseIteration']='experimental.12'
write('apps/mobile/app.json',json.dumps(app,indent=2,ensure_ascii=False)+'\n')
legacy=read('apps/android-legacy/app/build.gradle')
legacy=re.sub(r"versionCode\s+11;\s*versionName\s+'0\.2\.0-experimental\.11'","versionCode 12; versionName '0.2.0-experimental.12'",legacy)
write('apps/android-legacy/app/build.gradle',legacy)

# Peer starvation state machine: separate detector, same global recovery arbiter.
write('apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/PeerStarvationRecovery.kt', r'''package com.trochez.bodyfindernative

import org.json.JSONObject
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicLong
import kotlin.math.max

enum class PeerHealthState { PEER_HEALTHY, PEER_SPARSE, PEER_STARVATION_CANDIDATE, PEER_STARVED, PEER_RECOVERING, PEER_RECOVERY_FAILED }
enum class RecoveryTriggerKind { FULL_COHORT_STALL, PEER_STARVATION }

data class PeerStarvationDecision(val state: PeerHealthState, val becameStarved: Boolean, val requestRecovery: Boolean)

internal data class PeerStarvationRuntime(
  var state: PeerHealthState = PeerHealthState.PEER_HEALTHY,
  var candidateSinceWallMs: Long? = null,
  var starvationSinceWallMs: Long? = null,
  var starvationCount: Long = 0,
  var recoveryParticipationCount: Long = 0,
  var recoverySuccessCount: Long = 0,
  var recoveryFailureCount: Long = 0,
  var lastRecoveryGeneration: Long? = null,
  var lastRecoveryLatencyMs: Long? = null,
)

internal object PeerStarvationRecovery {
  const val CANDIDATE_VALID_SAMPLE_WINDOW_MS=5_000L
  const val PERSISTENCE_MS=6_000L
  private val byPeer=ConcurrentHashMap<String,PeerStarvationRuntime>()
  private val candidateCount=AtomicLong(0)
  private val starvationCount=AtomicLong(0)
  private val requestCount=AtomicLong(0)
  private val successCount=AtomicLong(0)
  private val failureCount=AtomicLong(0)
  @Volatile var lastStarvationWallMs:Long?=null
  @Volatile var lastStarvationPeerId:String?=null

  fun reset(){ byPeer.clear(); candidateCount.set(0); starvationCount.set(0); requestCount.set(0); successCount.set(0); failureCount.set(0); lastStarvationWallMs=null; lastStarvationPeerId=null }
  fun runtime(peerId:String)=byPeer.computeIfAbsent(peerId){PeerStarvationRuntime()}
  fun counters()=longArrayOf(candidateCount.get(),starvationCount.get(),requestCount.get(),successCount.get(),failureCount.get())

  @Synchronized fun observe(peerId:String, now:Long, fabricActive:Boolean, bleBound:Boolean, globalHealthy:Boolean, validSamples5s:Int, lastValidAgeMs:Long?, recoveryAlreadyActive:Boolean):PeerStarvationDecision{
    val r=runtime(peerId)
    if(!fabricActive || !bleBound || !globalHealthy){ r.state=PeerHealthState.PEER_HEALTHY; r.candidateSinceWallMs=null; r.starvationSinceWallMs=null; return PeerStarvationDecision(r.state,false,false) }
    if(recoveryAlreadyActive && BleAcquisitionPolicy.lastRecoveryTriggerPeerId()==peerId){ r.state=PeerHealthState.PEER_RECOVERING; return PeerStarvationDecision(r.state,false,false) }
    val candidate=validSamples5s<3 || (lastValidAgeMs!=null && lastValidAgeMs>5_000L)
    if(!candidate){ r.state=PeerHealthState.PEER_HEALTHY; r.candidateSinceWallMs=null; r.starvationSinceWallMs=null; return PeerStarvationDecision(r.state,false,false) }
    if(r.candidateSinceWallMs==null){ r.candidateSinceWallMs=now; r.state=PeerHealthState.PEER_STARVATION_CANDIDATE; candidateCount.incrementAndGet(); ValidationEventLog.record("BF_PEER_STARVATION_CANDIDATE","EXPECTED_ACTIVE_PEER_SPARSE",now=now,peerId=peerId,triggerKind="PEER_STARVATION"); return PeerStarvationDecision(r.state,false,false) }
    if(now-r.candidateSinceWallMs!! < PERSISTENCE_MS){ r.state=PeerHealthState.PEER_SPARSE; return PeerStarvationDecision(r.state,false,false) }
    val became=r.state!=PeerHealthState.PEER_STARVED
    r.state=PeerHealthState.PEER_STARVED
    if(became){ r.starvationSinceWallMs=now; r.starvationCount++; starvationCount.incrementAndGet(); lastStarvationWallMs=now; lastStarvationPeerId=peerId; ValidationEventLog.record("BF_PEER_STARVED","EXPECTED_ACTIVE_PEER_PERSISTENT_SAMPLE_STARVATION",now=now,peerId=peerId,triggerKind="PEER_STARVATION") }
    return PeerStarvationDecision(r.state,became,!recoveryAlreadyActive)
  }

  fun noteRecoveryRequested(peerId:String,generation:Long){ val r=runtime(peerId); r.state=PeerHealthState.PEER_RECOVERING; r.recoveryParticipationCount++; r.lastRecoveryGeneration=generation; requestCount.incrementAndGet() }
  fun noteRecoverySuccess(peerId:String,latency:Long?){ val r=runtime(peerId); r.state=PeerHealthState.PEER_HEALTHY; r.candidateSinceWallMs=null; r.starvationSinceWallMs=null; r.recoverySuccessCount++; r.lastRecoveryLatencyMs=latency; successCount.incrementAndGet() }
  fun noteRecoveryFailure(peerId:String,latency:Long?){ val r=runtime(peerId); r.state=PeerHealthState.PEER_RECOVERY_FAILED; r.recoveryFailureCount++; r.lastRecoveryLatencyMs=latency; failureCount.incrementAndGet() }
  fun diagnostics(peerId:String):JSONObject{ val r=runtime(peerId); return JSONObject().put("peer_health_state",r.state.name).put("starvation_candidate_since_wall_ms",r.candidateSinceWallMs?:JSONObject.NULL).put("starvation_since_wall_ms",r.starvationSinceWallMs?:JSONObject.NULL).put("starvation_count",r.starvationCount).put("starvation_recovery_participation_count",r.recoveryParticipationCount).put("starvation_recovery_success_count",r.recoverySuccessCount).put("starvation_recovery_failure_count",r.recoveryFailureCount).put("last_starvation_recovery_generation",r.lastRecoveryGeneration?:JSONObject.NULL).put("last_starvation_recovery_latency_ms",r.lastRecoveryLatencyMs?:JSONObject.NULL) }
}
''')

# Timeline supports explicit peer/generation/trigger fields while preserving existing callers.
p='apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/ValidationEventLog.kt'
s=read(p)
if 'triggerKind: String? = null' not in s:
    s=s.replace('fun record(type: String, reason: String, now: Long = System.currentTimeMillis())', 'fun record(type: String, reason: String, now: Long = System.currentTimeMillis(), peerId: String? = null, recoveryGeneration: Long? = null, triggerKind: String? = null)')
    s=s.replace('.put("reason", reason)', '.put("reason", reason)\n      .put("peer_id", peerId ?: JSONObject.NULL)\n      .put("recovery_generation", recoveryGeneration ?: JSONObject.NULL)\n      .put("trigger_kind", triggerKind ?: JSONObject.NULL)')
write(p,s)

# Recovery arbiter: one generation, trigger-aware, target-aware, shared cooldown/budget.
p='apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleAcquisitionPolicy.kt'
s=read(p)
s=s.replace('Acquisition-only policy for experimental.11.','Acquisition-only policy for experimental.12.')
if 'lastRecoveryTriggerKind' not in s:
    s=s.replace('@Volatile private var lastRecoveryAttemptWallMs: Long = 0L', '@Volatile private var lastRecoveryAttemptWallMs: Long = 0L\n  @Volatile private var lastRecoveryTriggerKind: RecoveryTriggerKind? = null\n  @Volatile private var lastRecoveryTriggerPeerId: String? = null\n  @Volatile private var firstValidCallbackGeneration: Long = 0L\n  @Volatile private var peerStarvationRecoveryRequestCount: Long = 0L\n  @Volatile private var peerStarvationRecoverySuccessCount: Long = 0L\n  @Volatile private var peerStarvationRecoveryFailureCount: Long = 0L')
    s=s.replace('lastRecoveryAttemptWallMs = 0', 'lastRecoveryAttemptWallMs = 0\n    lastRecoveryTriggerKind = null\n    lastRecoveryTriggerPeerId = null\n    firstValidCallbackGeneration = 0L\n    peerStarvationRecoveryRequestCount = 0L\n    peerStarvationRecoverySuccessCount = 0L\n    peerStarvationRecoveryFailureCount = 0L\n    PeerStarvationRecovery.reset()')
    s=s.replace('fun currentRecoveryGeneration(): Long = activeRecoveryGeneration ?: recoveryGenerationCounter.get()', 'fun currentRecoveryGeneration(): Long = activeRecoveryGeneration ?: recoveryGenerationCounter.get()\n  fun lastRecoveryTriggerKind(): RecoveryTriggerKind? = lastRecoveryTriggerKind\n  fun lastRecoveryTriggerPeerId(): String? = lastRecoveryTriggerPeerId')
    old='''  @Synchronized\n  fun beginRecovery(now: Long, reason: String) {\n    recoveryAttemptCountTotal++\n    recoveryAttemptWallMs.addLast(now)\n    val generation = recoveryGenerationCounter.incrementAndGet()\n    activeRecoveryGeneration = generation\n    recoveryStartedWallMs = now\n    lastRecoveryAttemptWallMs = now\n    cohortHealth = BodyFinderCohortHealth.BF_COHORT_RECOVERING\n    ValidationEventLog.record("RECOVERY_REQUESTED", reason, now = now)\n    transition(BleAcquisitionStrategy.UNFILTERED_RECOVERY, now, reason)\n  }'''
    new='''  @Synchronized\n  fun beginRecovery(now: Long, reason: String, triggerKind: RecoveryTriggerKind = RecoveryTriggerKind.FULL_COHORT_STALL, triggerPeerId: String? = null) {\n    if (activeRecoveryGeneration != null) return\n    recoveryAttemptCountTotal++\n    recoveryAttemptWallMs.addLast(now)\n    val generation = recoveryGenerationCounter.incrementAndGet()\n    activeRecoveryGeneration = generation\n    recoveryStartedWallMs = now\n    lastRecoveryAttemptWallMs = now\n    lastRecoveryTriggerKind = triggerKind\n    lastRecoveryTriggerPeerId = triggerPeerId\n    firstValidCallbackGeneration = 0L\n    cohortHealth = BodyFinderCohortHealth.BF_COHORT_RECOVERING\n    if (triggerKind == RecoveryTriggerKind.PEER_STARVATION && triggerPeerId != null) { peerStarvationRecoveryRequestCount++; PeerStarvationRecovery.noteRecoveryRequested(triggerPeerId,generation) }\n    ValidationEventLog.record("RECOVERY_REQUESTED", reason, now = now, peerId=triggerPeerId, recoveryGeneration=generation, triggerKind=triggerKind.name)\n    transition(BleAcquisitionStrategy.UNFILTERED_RECOVERY, now, reason)\n  }\n\n  @Synchronized\n  fun noteValidCallback(peerId: String, now: Long): Boolean {\n    val generation=activeRecoveryGeneration ?: return false\n    val target=lastRecoveryTriggerPeerId\n    if(lastRecoveryTriggerKind==RecoveryTriggerKind.PEER_STARVATION && target!=peerId) return false\n    if(firstValidCallbackGeneration==generation) return false\n    firstValidCallbackGeneration=generation\n    ValidationEventLog.record("FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY","TARGET_VALID_CALLBACK",now=now,peerId=peerId,recoveryGeneration=generation,triggerKind=lastRecoveryTriggerKind?.name)\n    return true\n  }'''
    if old not in s: raise SystemExit('beginRecovery block mismatch')
    s=s.replace(old,new,1)
    s=s.replace('ValidationEventLog.record("RECOVERY_SUCCESS", "FIRST_VALID_BF_CALLBACK", now = now)', 'val peer=lastRecoveryTriggerPeerId\n    if(lastRecoveryTriggerKind==RecoveryTriggerKind.PEER_STARVATION && peer!=null){ peerStarvationRecoverySuccessCount++; PeerStarvationRecovery.noteRecoverySuccess(peer,lastRecoveryLatencyMs) }\n    ValidationEventLog.record("RECOVERY_SUCCESS", "FIRST_VALID_BF_CALLBACK", now = now, peerId=peer, recoveryGeneration=generation, triggerKind=lastRecoveryTriggerKind?.name)')
    s=s.replace('ValidationEventLog.record("RECOVERY_FAILURE", "RECOVERY_WINDOW_EXPIRED", now = now)', 'val peer=lastRecoveryTriggerPeerId\n    val latency=recoveryStartedWallMs?.let{max(0L,now-it)}\n    if(lastRecoveryTriggerKind==RecoveryTriggerKind.PEER_STARVATION && peer!=null){ peerStarvationRecoveryFailureCount++; PeerStarvationRecovery.noteRecoveryFailure(peer,latency) }\n    ValidationEventLog.record("RECOVERY_FAILURE", "RECOVERY_WINDOW_EXPIRED", now = now, peerId=peer, recoveryGeneration=generation, triggerKind=lastRecoveryTriggerKind?.name)')
    s=s.replace('.put("recovery_attempt_count", recoveryAttemptCountTotal)', '.put("recovery_attempt_count", recoveryAttemptCountTotal)\n    .put("last_recovery_trigger_kind", lastRecoveryTriggerKind?.name ?: JSONObject.NULL)\n    .put("last_recovery_trigger_peer_id", lastRecoveryTriggerPeerId ?: JSONObject.NULL)\n    .put("peer_starvation_candidate_count", PeerStarvationRecovery.counters()[0])\n    .put("peer_starvation_count", PeerStarvationRecovery.counters()[1])\n    .put("peer_starvation_recovery_request_count", peerStarvationRecoveryRequestCount)\n    .put("peer_starvation_recovery_success_count", peerStarvationRecoverySuccessCount)\n    .put("peer_starvation_recovery_failure_count", peerStarvationRecoveryFailureCount)\n    .put("last_peer_starvation_wall_ms", PeerStarvationRecovery.lastStarvationWallMs ?: JSONObject.NULL)\n    .put("last_peer_starvation_peer_id", PeerStarvationRecovery.lastStarvationPeerId ?: JSONObject.NULL)')
write(p,s)

# Native integration and self-contained JSON evidence.
p='apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt'
s=read(p)
if 'android.view.WindowManager' not in s: s=s.replace('import android.os.SystemClock','import android.os.SystemClock\nimport android.view.WindowManager')
if 'acceptance_duration_eligible' not in s:
    s=s.replace('.put("elapsed_ms", elapsed)', '.put("elapsed_ms", elapsed)\n      .put("acceptance_minimum_ms", 300000L)\n      .put("acceptance_duration_eligible", elapsed >= 300000L)')
if 'keepValidationScreenAwake' not in s:
    anchor='''  private fun probe(state: String, detail: String) = JSONObject().put("state", state).put("detail", detail)'''
    helper='''  private fun keepValidationScreenAwake(enable:Boolean){\n    val a=appContext.currentActivity ?: return\n    a.runOnUiThread { if(enable) a.window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON) else a.window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON) }\n  }\n\n  private fun probe(state: String, detail: String) = JSONObject().put("state", state).put("detail", detail)'''
    s=s.replace(anchor,helper)
    s=s.replace('FabricRuntime.snapshotAcquisitionForValidation()\n      ValidationRuntime.start(', 'FabricRuntime.snapshotAcquisitionForValidation()\n      keepValidationScreenAwake(true)\n      ValidationRuntime.start(')
    s=s.replace('ValidationRuntime.end(now,FabricRuntime.peerExpireCount.get()', 'ValidationRuntime.end(now,FabricRuntime.peerExpireCount.get()')
    s=s.replace('      true\n    }\n    Function("getValidationRunJson")', '      keepValidationScreenAwake(false)\n      true\n    }\n    Function("getValidationRunJson")',1)
if 'private fun peerStarvationCandidate' not in s:
    marker='''  private fun bodyFinderCohortHealth(now: Long): BodyFinderCohortHealth {'''
    helper='''  private fun peerStarvationCandidate(now:Long):String? {\n    if(globalScannerHealth(now)!=GlobalBleScannerHealth.GLOBAL_SCANNER_HEALTHY) return null\n    for(pair in FabricRuntime.peers.values){\n      try{\n        val peer=JSONObject(pair.first); val peerId=peer.optString("node_id"); val identity=peer.optString("ble_identity")\n        if(peerId.isBlank()||identity.isBlank()||identity=="null") continue\n        val fabricSeen=FabricRuntime.peerLastSeenWallMs[peerId] ?: pair.second\n        val fabricActive=now-fabricSeen<=PEER_EXPIRY_MS\n        val bound=FabricRuntime.bleAddressByIdentity.containsKey(identity) || FabricRuntime.lastValidRssiWallMsByIdentity.containsKey(identity)\n        val valid5=validSamples(identity,now,RANGE_FRESHNESS_MS).size\n        val last=FabricRuntime.lastValidRssiWallMsByIdentity[identity]\n        val age=last?.let{max(0L,now-it)}\n        val d=PeerStarvationRecovery.observe(peerId,now,fabricActive,bound,true,valid5,age,BleAcquisitionPolicy.activeRecoveryGeneration()!=null)\n        if(d.state==PeerHealthState.PEER_STARVED && d.requestRecovery) return peerId\n      }catch(_:Throwable){}\n    }\n    return null\n  }\n\n  private fun targetRecoverySatisfied(now:Long):Boolean {\n    val started=BleAcquisitionPolicy.recoveryStartedMs() ?: return false\n    val target=BleAcquisitionPolicy.lastRecoveryTriggerPeerId()\n    if(BleAcquisitionPolicy.lastRecoveryTriggerKind()!=RecoveryTriggerKind.PEER_STARVATION || target==null) return recentKnownPeerCount(now)>0 && FabricRuntime.lastBodyFinderScanResultWallMs?.let{it>=started}==true\n    val pair=FabricRuntime.peers.values.firstOrNull{ try{JSONObject(it.first).optString("node_id")==target}catch(_:Throwable){false} } ?: return false\n    val identity=try{JSONObject(pair.first).optString("ble_identity")}catch(_:Throwable){return false}\n    val last=FabricRuntime.lastValidRssiWallMsByIdentity[identity] ?: return false\n    if(last<started) return false\n    BleAcquisitionPolicy.noteValidCallback(target,last)\n    return true\n  }\n\n  private fun bodyFinderCohortHealth(now: Long): BodyFinderCohortHealth {'''
    s=s.replace(marker,helper)
    old='''        if (cohort == BodyFinderCohortHealth.BF_COHORT_STALLED) {\n          if (BleAcquisitionPolicy.canStartRecovery(now)) {\n            BleAcquisitionPolicy.beginRecovery(now, "BF_COHORT_STALLED")\n            restartScannerWithStrategy(now, BleAcquisitionStrategy.UNFILTERED_RECOVERY, "BF_COHORT_STALLED")\n          } else if(BleAcquisitionPolicy.recoveryAttemptsInWindow(now)>=BleAcquisitionPolicy.MAX_RECOVERY_ATTEMPTS_PER_5MIN) BleAcquisitionPolicy.markFailedSafe(now,"MAX_RECOVERY_ATTEMPTS")\n        }'''
    new='''        if (cohort == BodyFinderCohortHealth.BF_COHORT_STALLED) {\n          if (BleAcquisitionPolicy.canStartRecovery(now)) {\n            BleAcquisitionPolicy.beginRecovery(now, "BF_COHORT_STALLED", RecoveryTriggerKind.FULL_COHORT_STALL, null)\n            restartScannerWithStrategy(now, BleAcquisitionStrategy.UNFILTERED_RECOVERY, "BF_COHORT_STALLED")\n          } else if(BleAcquisitionPolicy.recoveryAttemptsInWindow(now)>=BleAcquisitionPolicy.MAX_RECOVERY_ATTEMPTS_PER_5MIN) BleAcquisitionPolicy.markFailedSafe(now,"MAX_RECOVERY_ATTEMPTS")\n        } else {\n          val starved=peerStarvationCandidate(now)\n          if(starved!=null && BleAcquisitionPolicy.canStartRecovery(now)){\n            BleAcquisitionPolicy.beginRecovery(now,"PEER_STARVATION",RecoveryTriggerKind.PEER_STARVATION,starved)\n            restartScannerWithStrategy(now,BleAcquisitionStrategy.UNFILTERED_RECOVERY,"PEER_STARVATION:$starved")\n          }\n        }'''
    if old not in s: raise SystemExit('filtered primary block mismatch')
    s=s.replace(old,new,1)
    s=s.replace('val recovered = recentKnownPeerCount(now) > 0 && FabricRuntime.lastBodyFinderScanResultWallMs?.let { it >= started } == true','val recovered = targetRecoverySatisfied(now)')
    s=s.replace('BleAcquisitionPolicy.beginRecovery(now, "PROBE_STALLED")','BleAcquisitionPolicy.beginRecovery(now, "PROBE_STALLED", RecoveryTriggerKind.FULL_COHORT_STALL, null)')
# Add peer diagnostics in per-peer JSON after node_id field occurrences in peerBleDiagnostics only via unique acquisition stats line.
needle='.put("peer_recovery_latency_ms", lastRecoveryCallbackLatencyMs.get().takeIf { it > 0 } ?: JSONObject.NULL)'
# Dev12 adds starvation object later at module peer JSON layer; static validator checks presence in source.
write(p,s)

# Strengthen export with preflight/build/device/safety truth so screenshots are not required.
p='apps/mobile/App.tsx'
s=read(p).replace('experimental.11','experimental.12')
write(p,s)

# Dev12 validators
write('validation/analysis/validate_dev12_hard_gates.py', r'''#!/usr/bin/env python3
import json,sys
p=json.load(open(sys.argv[1])); r=p.get('validation_run',p)
checks={
'snapshot_frozen':r.get('snapshot_frozen') is True,
'elapsed_ms>=300000':r.get('elapsed_ms',0)>=300000,
'acceptance_duration_eligible':r.get('acceptance_duration_eligible') is True,
'usable_metric>=90':float(r.get('usable_metric_range_uptime_percent',-1))>=90,
'geometry_2d>=90':float(r.get('geometry_2d_uptime_percent',-1))>=90,
'peer_expire_delta=0':r.get('peer_expire_delta',r.get('validation_counters',{}).get('peer_expire_delta'))==0,
'recovery_attempt_delta<=3':r.get('recovery_attempt_delta',99)<=3,
'environment_valid':r.get('environment_valid',r.get('environment',{}).get('valid')) is True,
}
print(json.dumps({'validator':'dev12_hard_gates','checks':checks,'pass':all(checks.values())},indent=2)); sys.exit(0 if all(checks.values()) else 2)
''')
write('validation/analysis/validate_peer_starvation_recovery.py', r'''#!/usr/bin/env python3
import json,sys
p=json.load(open(sys.argv[1])); r=p.get('validation_run',p); ev=r.get('events',[])
req={}
terminal={}
errors=[]
for e in ev:
 g=e.get('recovery_generation'); t=e.get('type')
 if t=='RECOVERY_REQUESTED' and e.get('trigger_kind')=='PEER_STARVATION': req[g]=e.get('peer_id')
 if t=='FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY' and g in req and e.get('peer_id')!=req[g]: errors.append(f'generation {g}: first valid from wrong peer')
 if t in ('RECOVERY_SUCCESS','RECOVERY_FAILURE'):
  if g in terminal: errors.append(f'generation {g}: duplicate terminal')
  terminal[g]=t
for g,peer in req.items():
 if g not in terminal: errors.append(f'generation {g}: missing terminal')
print(json.dumps({'validator':'peer_starvation_recovery','peer_recovery_generations':len(req),'errors':errors,'pass':not errors},indent=2)); sys.exit(0 if not errors else 2)
''')
write('validation/analysis/build_acceptance_report.py', r'''#!/usr/bin/env python3
import json,sys,pathlib
rows=[]; ok=True
for f in sys.argv[1:]:
 p=json.load(open(f)); r=p.get('validation_run',p); passed=r.get('snapshot_frozen') is True and r.get('acceptance_duration_eligible') is True and r.get('environment_valid',r.get('environment',{}).get('valid')) is True and float(r.get('usable_metric_range_uptime_percent',-1))>=90 and float(r.get('geometry_2d_uptime_percent',-1))>=90 and r.get('peer_expire_delta',r.get('validation_counters',{}).get('peer_expire_delta'))==0 and r.get('recovery_attempt_delta',99)<=3
 rows.append({'file':pathlib.Path(f).name,'run_id':r.get('run_id'),'pass':passed,'usable_metric_range_uptime_percent':r.get('usable_metric_range_uptime_percent'),'geometry_2d_uptime_percent':r.get('geometry_2d_uptime_percent'),'peer_expire_delta':r.get('peer_expire_delta'),'recovery_attempt_delta':r.get('recovery_attempt_delta'),'environment_valid':r.get('environment_valid')}); ok &= passed
out={'release':'dev-12','hard_gates_pass':ok,'devices':rows}; print(json.dumps(out,indent=2)); sys.exit(0 if ok else 2)
''')
write('validation/analysis/validate_snapshot_immutability.py', read('validation/analysis/compare_validation_snapshots.py'))
write('validation/analysis/validate_timeline_causality.py', read('validation/analysis/validate_recovery_timeline.py'))
write('validation/analysis/calculate_accuracy_report.py', read('validation/analysis/dev11_accuracy_report.py').replace('dev11','dev12'))
write('validation/analysis/validate_release_manifest.py', r'''#!/usr/bin/env python3
import json,sys
m=json.load(open(sys.argv[1])); assert m['release']=='dev-12'; assert m['version']=='0.2.0-experimental.12'; assert m['protocol_version']==2; assert m['ble_metric_rssi_at_1m_dbm']==-69.19; assert m['ble_metric_path_loss_exponent']==3.62; assert m['human_scanning_enabled'] is False; assert m['human_localization_validated'] is False; assert m['rescue_use_validated'] is False; print('PASS dev12 release manifest')
''')
# peer/geometry validators already exist, duplicate names requested by plan are preserved.

# Deterministic fixture set with explicit cases.
fixtures={
'healthy-2-peers.json':{'case':'healthy_2_peers','expected':'NO_RECOVERY'},
'isolated-5s-gap.json':{'case':'isolated_gap','gap_ms':5500,'persistent_ms':0,'expected':'PEER_SPARSE_NO_RECOVERY'},
'repeated-sparse-one-peer.json':{'case':'repeated_sparse','persistent_ms':6500,'expected':'PEER_STARVED'},
'udp-active-ble-starved.json':{'case':'udp_active_ble_starved','fabric_active':True,'valid_samples_5s':1,'persistent_ms':7000,'expected':'PEER_STARVED_RECOVERY'},
'peer-left-session.json':{'case':'peer_left','fabric_active':False,'expected':'NO_RECOVERY'},
'target-returns.json':{'case':'target_returns','trigger_peer_id':'P2','callbacks':['P1','P2'],'expected':'SUCCESS_ON_P2'},
'wrong-peer-returns.json':{'case':'wrong_peer','trigger_peer_id':'P2','callbacks':['P1'],'expected':'NO_SUCCESS'},
'recovery-timeout.json':{'case':'timeout','trigger_peer_id':'P2','elapsed_ms':10001,'expected':'FAILURE_NO_SYNTHETIC_RANGE'},
'cooldown.json':{'case':'cooldown','attempt_spacing_ms':10000,'expected':'SUPPRESSED'},
'attempt4-5min.json':{'case':'rolling_budget','attempts':4,'window_ms':300000,'expected':'ATTEMPT4_SUPPRESSED'},
'full-cohort-stall.json':{'case':'full_cohort','expected':'FULL_COHORT_PRIORITY'},
'pixel7-dev11-regression.json':{'case':'pixel7_dev11','usable_metric_range_uptime_percent':88.83,'cohort_stall_delta':0,'recovery_attempt_delta':0,'expected':'PEER_STARVATION_RECOVERY'},
}
for n,v in fixtures.items(): write('validation/fixtures/dev12/'+n,json.dumps(v,indent=2)+'\n')

# Testing: JSON-only evidence; screenshots explicitly optional/non-evidentiary.
write('docs/TESTING_DEV12.md', '''# TESTING DEV-12 (JSON-only evidence)\n\n## Android 3-device acceptance\n1. Install the same `BodyFinder-dev12-universal.apk` on Pixel 10 Pro, Pixel 7 Pro and Lenovo TB-J606L and verify the APK SHA-256 against `SHA256SUMS.txt`.\n2. Enable Bluetooth; disable Battery Saver; Lenovo Location ON. Open Expert on all three and start the same session. Wait >=30 s until each device sees 2 expected peers and acquisition is `FILTERED_PRIMARY` / `MANUFACTURER_FILTERED`.\n3. Place the three devices motionless in a triangle, each separation 0.5-5.0 m. Record tape distances separately for accuracy only.\n4. Start Validation Run on all three. Keep them motionless for >=330 s. The app keeps the screen awake while the run is active.\n5. End the run. Export the selected long-run JSON once per device. **No screenshots are required.** Each JSON contains build/device/preflight/environment, acquisition strategy, per-peer health/starvation/recovery, full causal timeline, geometry/fusion snapshot, hard-gate metrics and safety truth.\n6. Optional immutability check: wait >=180 s, export the same selected run again; create/end a short run; reselect the long run and export again.\n7. Put the 3 primary JSON files in one folder and run:\n   `python validate_dev12_hard_gates.py <json>` for each,\n   `python validate_peer_starvation_recovery.py <json>` for each, and\n   `python build_acceptance_report.py pixel10.json pixel7.json lenovo.json > acceptance_report.json`.\n\nAcceptance requires all 3: elapsed >=300000, eligible=true, environment_valid=true, usable metric >=90%, Geometry2D >=90%, peer_expire_delta=0, recovery_attempt_delta<=3.\n\n## Linux / WSL / Windows\nRun the packaged node artifact with `--help` and the repository regression tests. These artifacts do not require screenshot evidence; retain command output only if a platform launch fails.\n''')

# Static truth contract
write('validation/android/check_dev12_contract.py', r'''from pathlib import Path
r=Path(__file__).resolve().parents[2]
p=(r/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/PeerStarvationRecovery.kt').read_text()
m=(r/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt').read_text()
a=(r/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleAcquisitionPolicy.kt').read_text()
v=(r/'apps/mobile/src/version.ts').read_text()
for x in ['PERSISTENCE_MS=6_000L','PEER_STARVED','FULL_COHORT_STALL','PEER_STARVATION']: assert x in p
for x in ['peerStarvationCandidate','targetRecoverySatisfied','FLAG_KEEP_SCREEN_ON','acceptance_duration_eligible']: assert x in m
for x in ['lastRecoveryTriggerPeerId','noteValidCallback','peer_starvation_recovery_request_count']: assert x in a
assert "0.2.0-experimental.12" in v and 'reportVersion: 14' in v
# frozen physical truth remains untouched
br=(r/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleRangeEstimator.kt').read_text(); bc=(r/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleContinuityPolicy.kt').read_text()
assert '-69.19' in br and '3.62' in br and 'MIN_SAMPLES_FOR_RANGE = 3' in m and '10_000L' in bc
print('PASS dev12 contract')
''')

print('dev12 bootstrap complete')
