#!/usr/bin/env python3
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
def read(p): return (ROOT/p).read_text()
def write(p, s):
    q=ROOT/p; q.parent.mkdir(parents=True, exist_ok=True); q.write_text(s)
def once(s, old, new, label):
    n=s.count(old)
    if n != 1: raise RuntimeError(f'{label}: expected 1 match, got {n}')
    return s.replace(old,new,1)

# ---- release identity -------------------------------------------------------
p='apps/mobile/src/version.ts'; s=read(p)
s=s.replace("0.2.0-experimental.15","0.2.0-experimental.16").replace('reportVersion: 17','reportVersion: 18').replace('versionCode: 15','versionCode: 16').replace("releaseIteration: 'experimental.15'","releaseIteration: 'experimental.16'").replace('snapshotSchemaVersion: 3','snapshotSchemaVersion: 4')
write(p,s)
p='apps/mobile/app.json'; s=read(p).replace('"versionCode": 15','"versionCode": 16').replace('"releaseIteration": "experimental.15"','"releaseIteration": "experimental.16"'); write(p,s)

# ---- Android recovery clock/deadline contract ------------------------------
p='apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleAcquisitionPolicy.kt'; s=read(p)
s=s.replace('import android.os.Build\n','import android.os.Build\nimport android.os.SystemClock\n').replace('Acquisition-only policy for experimental.15.','Acquisition-only policy for experimental.16.')
s=once(s,'  const val RECOVERY_UNFILTERED_WINDOW_MS = 10_000L\n  const val FILTERED_PROBE_WINDOW_MS = 15_000L\n  const val FILTERED_PROBE_EXIT_TARGET_MS = 14_500L\n', '  const val RECOVERY_UNFILTERED_WINDOW_MS = 10_000L\n  const val RECOVERY_UNFILTERED_ACTION_TARGET_MS = 9_500L\n  const val FILTERED_PROBE_WINDOW_MS = 15_000L\n  const val FILTERED_PROBE_EXIT_TARGET_MS = 14_500L\n  const val FILTERED_PROBE_ACTION_TARGET_MS = 14_000L\n','timing constants')
s=once(s,'  @Volatile private var recoveryStartedWallMs: Long? = null\n  @Volatile private var recoveryProbeStartedWallMs: Long? = null\n', '  @Volatile private var recoveryStartedWallMs: Long? = null\n  @Volatile private var recoveryStartedElapsedMs: Long? = null\n  @Volatile private var recoveryProbeStartedWallMs: Long? = null\n  @Volatile private var recoveryProbeStartedElapsedMs: Long? = null\n','monotonic state')
s=once(s,'  @Volatile private var recoveryAttemptCountTotal: Long = 0L\n', '  @Volatile private var recoveryAttemptCountTotal: Long = 0L\n  @Volatile private var maxRecoveryAttemptsInAnyRollingWindow: Int = 0\n','rolling max state')
s=once(s,'    recoveryAttemptCountTotal = 0\n    recoveryStartedWallMs = null\n    recoveryProbeStartedWallMs = null\n', '    recoveryAttemptCountTotal = 0\n    maxRecoveryAttemptsInAnyRollingWindow = 0\n    recoveryStartedWallMs = null\n    recoveryStartedElapsedMs = null\n    recoveryProbeStartedWallMs = null\n    recoveryProbeStartedElapsedMs = null\n','monotonic reset')
s=once(s,'  fun recoveryStartedMs(): Long? = recoveryStartedWallMs\n  fun recoveryProbeStartedMs(): Long? = recoveryProbeStartedWallMs\n', '  fun recoveryStartedMs(): Long? = recoveryStartedWallMs\n  fun recoveryUnfilteredElapsedMs(nowElapsedMs: Long = SystemClock.elapsedRealtime()): Long? = recoveryStartedElapsedMs?.let { max(0L, nowElapsedMs - it) }\n  fun recoveryProbeStartedMs(): Long? = recoveryProbeStartedWallMs\n  fun filteredProbeElapsedMs(nowElapsedMs: Long = SystemClock.elapsedRealtime()): Long? = recoveryProbeStartedElapsedMs?.let { max(0L, nowElapsedMs - it) }\n  fun maxRecoveryAttemptsInAnyRollingWindow(): Int = maxRecoveryAttemptsInAnyRollingWindow\n','monotonic getters')
s=once(s,'    if (next == BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE) {\n      recoveryProbeStartedWallMs = now\n      recoveryProbeDeadlineWallMs = now + FILTERED_PROBE_EXIT_TARGET_MS\n    }\n', '    if (next == BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE) {\n      recoveryProbeStartedWallMs = now\n      recoveryProbeStartedElapsedMs = SystemClock.elapsedRealtime()\n      recoveryProbeDeadlineWallMs = now + FILTERED_PROBE_EXIT_TARGET_MS\n    }\n','probe monotonic start')
s=once(s,'      recoveryStartedWallMs = null\n      recoveryProbeStartedWallMs = null\n      recoveryProbeDeadlineWallMs = null\n', '      recoveryStartedWallMs = null\n      recoveryStartedElapsedMs = null\n      recoveryProbeStartedWallMs = null\n      recoveryProbeStartedElapsedMs = null\n      recoveryProbeDeadlineWallMs = null\n','monotonic clear')
s=once(s,'    recoveryAttemptCountTotal++\n    recoveryAttemptWallMs.addLast(now)\n', '    recoveryAttemptCountTotal++\n    recoveryAttemptWallMs.addLast(now)\n    recoveryAttemptsInWindow(now)\n    maxRecoveryAttemptsInAnyRollingWindow = max(maxRecoveryAttemptsInAnyRollingWindow, recoveryAttemptWallMs.size)\n','rolling max update')
s=once(s,'    recoveryStartedWallMs = now\n    lastRecoveryAttemptWallMs = now\n', '    recoveryStartedWallMs = now\n    recoveryStartedElapsedMs = SystemClock.elapsedRealtime()\n    lastRecoveryAttemptWallMs = now\n','recovery monotonic start')
s=s.replace('      recoveryStartedWallMs = null\n    }\n    recoveryAttemptCountTotal++','      recoveryStartedWallMs = null\n      recoveryStartedElapsedMs = null\n    }\n    recoveryAttemptCountTotal++',1)
s=once(s,'    .put("recovery_unfiltered_window_ms", RECOVERY_UNFILTERED_WINDOW_MS)\n    .put("filtered_probe_window_ms", FILTERED_PROBE_WINDOW_MS)\n    .put("filtered_probe_exit_target_ms", FILTERED_PROBE_EXIT_TARGET_MS)\n', '    .put("recovery_unfiltered_window_ms", RECOVERY_UNFILTERED_WINDOW_MS)\n    .put("recovery_unfiltered_hard_limit_ms", RECOVERY_UNFILTERED_WINDOW_MS)\n    .put("recovery_unfiltered_action_target_ms", RECOVERY_UNFILTERED_ACTION_TARGET_MS)\n    .put("filtered_probe_window_ms", FILTERED_PROBE_WINDOW_MS)\n    .put("filtered_probe_hard_limit_ms", FILTERED_PROBE_WINDOW_MS)\n    .put("filtered_probe_exit_target_ms", FILTERED_PROBE_EXIT_TARGET_MS)\n    .put("filtered_probe_action_target_ms", FILTERED_PROBE_ACTION_TARGET_MS)\n','diagnostic timing fields')
s=once(s,'    .put("max_recovery_attempts_per_5min", MAX_RECOVERY_ATTEMPTS_PER_5MIN)\n', '    .put("max_recovery_attempts_per_5min", MAX_RECOVERY_ATTEMPTS_PER_5MIN)\n    .put("recovery_budget_window_ms", RECOVERY_ATTEMPT_WINDOW_MS)\n    .put("recovery_budget_limit", MAX_RECOVERY_ATTEMPTS_PER_5MIN)\n    .put("recovery_attempts_in_current_5min_window", recoveryAttemptsInWindow(now))\n    .put("recovery_attempts_max_in_any_rolling_5min_window", maxRecoveryAttemptsInAnyRollingWindow)\n','diagnostic budget fields')
write(p,s)

# ---- Android completed snapshot v4 ----------------------------------------
p='apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt'; s=read(p)
s=once(s,'  @Volatile private var usableMetricRangeUptimeMs: Long = 0\n', '  @Volatile private var usableMetricRangeUptimeMs: Long = 0\n  @Volatile private var singleRemotePeerMetricUptimeMs: Long = 0\n  @Volatile private var allExpectedPeerMetricUptimeMs: Long = 0\n','uptime states')
s=once(s,'    usableMetricRangeUptimeMs = 0\n', '    usableMetricRangeUptimeMs = 0\n    singleRemotePeerMetricUptimeMs = 0\n    allExpectedPeerMetricUptimeMs = 0\n','uptime reset')
s=once(s,'    if (usableMetricReadyPeerCount >= 2) usableMetricRangeUptimeMs += dt\n', '    if (usableMetricReadyPeerCount >= 2) usableMetricRangeUptimeMs += dt\n    if (usableMetricReadyPeerCount >= 1) singleRemotePeerMetricUptimeMs += dt\n    if (activePeerCount > 0 && usableMetricReadyPeerCount >= activePeerCount) allExpectedPeerMetricUptimeMs += dt\n','uptime observe')
s=once(s,'      .put("usable_metric_range_uptime_percent", pct(usableMetricRangeUptimeMs))\n', '      .put("usable_metric_range_uptime_percent", pct(usableMetricRangeUptimeMs))\n      .put("single_remote_peer_metric_uptime_percent", pct(singleRemotePeerMetricUptimeMs))\n      .put("all_expected_peer_metric_uptime_percent", pct(allExpectedPeerMetricUptimeMs))\n','uptime output')
s=s.replace('.put("snapshot_schema_version", 3)', '.put("snapshot_schema_version", 4)')
# Enrich the frozen acquisition object from run/event truth at End.
needle='''    val counters = JSONObject()\n      .put("peer_expire_delta", base.optLong("peer_expire_delta"))'''
insert='''    val requestWalls = mutableListOf<Long>()
    val generations = mutableMapOf<Long, MutableList<JSONObject>>()
    for (i in 0 until events.length()) {
      val e = events.optJSONObject(i) ?: continue
      val g = e.optLong("recovery_generation", Long.MIN_VALUE)
      if (g != Long.MIN_VALUE) generations.getOrPut(g) { mutableListOf() }.add(e)
      if (e.optString("type") == "RECOVERY_REQUESTED") requestWalls += e.optLong("wall_ms")
    }
    var rollingMax = 0
    requestWalls.sorted().forEach { start -> rollingMax = max(rollingMax, requestWalls.count { it >= start && it <= start + BleAcquisitionPolicy.RECOVERY_ATTEMPT_WINDOW_MS }) }
    var maxUnfiltered = 0L; var unfilteredTargetMisses = 0; var unfilteredBreaches = 0
    var maxProbe = 0L; var probeTargetMisses = 0; var probeBreaches = 0
    generations.values.forEach { group ->
      val request = group.firstOrNull { it.optString("type") == "RECOVERY_REQUESTED" }
      val terminal = group.firstOrNull { it.optString("type") == "RECOVERY_SUCCESS" || it.optString("type") == "RECOVERY_FAILURE" }
      if (request != null && terminal != null) {
        val d = max(0L, terminal.optLong("wall_ms") - request.optLong("wall_ms")); maxUnfiltered = max(maxUnfiltered,d)
        if (d > BleAcquisitionPolicy.RECOVERY_UNFILTERED_ACTION_TARGET_MS) unfilteredTargetMisses++
        if (d > BleAcquisitionPolicy.RECOVERY_UNFILTERED_WINDOW_MS) unfilteredBreaches++
      }
      val ps = group.firstOrNull { it.optString("type") == "ACQUISITION_STRATEGY_CHANGED" && it.optString("to_strategy") == "FILTERED_RECOVERY_PROBE" }
      val pe = group.firstOrNull { it.optString("type") == "ACQUISITION_STRATEGY_CHANGED" && it.optString("from_strategy") == "FILTERED_RECOVERY_PROBE" }
      if (ps != null) {
        val d = max(0L, (pe?.optLong("wall_ms") ?: now) - ps.optLong("wall_ms")); maxProbe=max(maxProbe,d)
        if (d > BleAcquisitionPolicy.FILTERED_PROBE_EXIT_TARGET_MS) probeTargetMisses++
        if (d > BleAcquisitionPolicy.FILTERED_PROBE_WINDOW_MS) probeBreaches++
      }
    }
    acquisitionState
      .put("recovery_unfiltered_hard_limit_ms", BleAcquisitionPolicy.RECOVERY_UNFILTERED_WINDOW_MS)
      .put("recovery_unfiltered_action_target_ms", BleAcquisitionPolicy.RECOVERY_UNFILTERED_ACTION_TARGET_MS)
      .put("filtered_probe_exit_target_ms", BleAcquisitionPolicy.FILTERED_PROBE_EXIT_TARGET_MS)
      .put("filtered_probe_hard_limit_ms", BleAcquisitionPolicy.FILTERED_PROBE_WINDOW_MS)
      .put("filtered_probe_action_target_ms", BleAcquisitionPolicy.FILTERED_PROBE_ACTION_TARGET_MS)
      .put("recovery_budget_window_ms", BleAcquisitionPolicy.RECOVERY_ATTEMPT_WINDOW_MS)
      .put("recovery_budget_limit", BleAcquisitionPolicy.MAX_RECOVERY_ATTEMPTS_PER_5MIN)
      .put("recovery_attempt_delta_total", base.optLong("recovery_attempt_delta"))
      .put("recovery_attempts_in_current_5min_window_at_end", requestWalls.count { now - it <= BleAcquisitionPolicy.RECOVERY_ATTEMPT_WINDOW_MS })
      .put("recovery_attempts_max_in_any_rolling_5min_window", rollingMax)
    val timingSummary = JSONObject()
      .put("generation_count", generations.size)
      .put("max_unfiltered_duration_ms", maxUnfiltered)
      .put("unfiltered_action_target_miss_count", unfilteredTargetMisses)
      .put("unfiltered_hard_limit_breach_count", unfilteredBreaches)
      .put("max_filtered_probe_duration_ms", maxProbe)
      .put("filtered_probe_target_miss_count", probeTargetMisses)
      .put("filtered_probe_hard_limit_breach_count", probeBreaches)

    val counters = JSONObject()
      .put("peer_expire_delta", base.optLong("peer_expire_delta"))'''
s=once(s,needle,insert,'snapshot event summaries')
s=once(s,'      .put("acquisition_state_at_end", acquisitionState)\n', '      .put("acquisition_state_at_end", acquisitionState)\n      .put("recovery_timing_summary", timingSummary)\n','timing summary attach')
# Add all frozen acquisition fields to provenance too (live/frozen field parity).
s=once(s,'      .put("recovery_started_wall_ms", BleAcquisitionPolicy.recoveryStartedMs() ?: JSONObject.NULL)\n', '      .put("recovery_started_wall_ms", BleAcquisitionPolicy.recoveryStartedMs() ?: JSONObject.NULL)\n      .put("recovery_unfiltered_hard_limit_ms", BleAcquisitionPolicy.RECOVERY_UNFILTERED_WINDOW_MS)\n      .put("recovery_unfiltered_action_target_ms", BleAcquisitionPolicy.RECOVERY_UNFILTERED_ACTION_TARGET_MS)\n      .put("filtered_probe_exit_target_ms", BleAcquisitionPolicy.FILTERED_PROBE_EXIT_TARGET_MS)\n      .put("filtered_probe_hard_limit_ms", BleAcquisitionPolicy.FILTERED_PROBE_WINDOW_MS)\n      .put("filtered_probe_action_target_ms", BleAcquisitionPolicy.FILTERED_PROBE_ACTION_TARGET_MS)\n      .put("recovery_budget_window_ms", BleAcquisitionPolicy.RECOVERY_ATTEMPT_WINDOW_MS)\n      .put("recovery_budget_limit", BleAcquisitionPolicy.MAX_RECOVERY_ATTEMPTS_PER_5MIN)\n      .put("recovery_attempts_in_current_5min_window_at_end", BleAcquisitionPolicy.recoveryAttemptsInWindow(now))\n      .put("recovery_attempts_max_in_any_rolling_5min_window", BleAcquisitionPolicy.maxRecoveryAttemptsInAnyRollingWindow())\n','provenance contract fields')
# Enforce action targets before environment evaluation, using monotonic age from policy.
needle='''    BleAcquisitionPolicy.updateCohortHealth(cohort, now)\n\n    if (global == GlobalBleScannerHealth.GLOBAL_SCANNER_STALLED) {'''
insert='''    BleAcquisitionPolicy.updateCohortHealth(cohort, now)

    // dev16: action targets use elapsedRealtime internally; wall_ms remains evidence only.
    if (BleAcquisitionPolicy.currentStrategy() == BleAcquisitionStrategy.UNFILTERED_RECOVERY &&
        (BleAcquisitionPolicy.recoveryUnfilteredElapsedMs() ?: 0L) >= BleAcquisitionPolicy.RECOVERY_UNFILTERED_ACTION_TARGET_MS) {
      val triggerPeer = BleAcquisitionPolicy.activeRecoveryTriggerPeerId()
      val triggerKind = BleAcquisitionPolicy.activeRecoveryTriggerKind()
      BleAcquisitionPolicy.noteRecoveryFailure(now)
      if (triggerPeer != null && triggerKind == RecoveryTriggerKind.PEER_STARVATION) {
        FabricRuntime.peerHealthStateByPeer[triggerPeer] = PeerHealthState.PEER_RECOVERY_FAILED.name
        FabricRuntime.peerStarvationRecoveryFailureByPeer.computeIfAbsent(triggerPeer) { AtomicLong(0) }.incrementAndGet()
      }
      restartScannerWithStrategy(now, BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE, "RECOVERY_ACTION_TARGET_EXPIRED")
      return
    }
    if (BleAcquisitionPolicy.currentStrategy() == BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE &&
        (BleAcquisitionPolicy.filteredProbeElapsedMs() ?: 0L) >= BleAcquisitionPolicy.FILTERED_PROBE_ACTION_TARGET_MS) {
      BleAcquisitionPolicy.transition(BleAcquisitionStrategy.FILTERED_PRIMARY, now, "PROBE_ACTION_TARGET")
      restartScannerWithStrategy(now, BleAcquisitionStrategy.FILTERED_PRIMARY, "PROBE_ACTION_TARGET")
      return
    }

    if (global == GlobalBleScannerHealth.GLOBAL_SCANNER_STALLED) {'''
s=once(s,needle,insert,'monotonic action enforcement')
# Explicit live preflight non-acceptance source and coherent contracts.
s=s.replace('.put("schema", "dev13-self-contained-json-evidence-v2")','.put("schema", "dev16-self-contained-json-evidence-v4")')
s=once(s,'.put("validation_preflight", validationPreflight(ctx, now))\n', '.put("validation_preflight", validationPreflight(ctx, now).put("runtime_live", true).put("not_acceptance_evidence", true))\n      .put("evidence_contract", JSONObject().put("schema", "dev16-self-contained-json-evidence-v4").put("screenshots_required", false).put("json_self_contained", true))\n','live preflight contract')
write(p,s)

# ---- JS export identity -----------------------------------------------------
p='apps/mobile/App.tsx'; s=read(p).replace('experimental.15','experimental.16').replace("dev15-self-contained-json-evidence-v3","dev16-self-contained-json-evidence-v4")
write(p,s)

# ---- Snapshot JSON schema v4 -----------------------------------------------
schema={
 '$schema':'https://json-schema.org/draft/2020-12/schema','title':'Body Finder completed validation run snapshot v4','type':'object',
 'required':['snapshot_schema_version','snapshot_frozen','run_id','started_wall_ms','ended_wall_ms','elapsed_ms','preflight_at_start','environment','validation_counters','acquisition_state_at_end','recovery_timing_summary','per_peer_at_end','system_ranging_at_end','events','geometry_at_end','fused_range_observations_at_end'],
 'properties':{
  'snapshot_schema_version':{'const':4},'snapshot_frozen':{'const':True},'run_id':{'type':'string','minLength':1},
  'started_wall_ms':{'type':'number'},'ended_wall_ms':{'type':'number'},'elapsed_ms':{'type':'number','minimum':0},
  'preflight_at_start':{'type':'object'},'environment':{'type':'object'},'validation_counters':{'type':'object'},
  'acquisition_state_at_end':{'type':'object','required':['logical_acquisition_strategy','active_recovery_generation','strategy_recovery_generation','recovery_unfiltered_hard_limit_ms','recovery_unfiltered_action_target_ms','filtered_probe_exit_target_ms','filtered_probe_hard_limit_ms','filtered_probe_action_target_ms','recovery_budget_window_ms','recovery_budget_limit','recovery_attempt_delta_total','recovery_attempts_in_current_5min_window_at_end','recovery_attempts_max_in_any_rolling_5min_window']},
  'recovery_timing_summary':{'type':'object','required':['generation_count','max_unfiltered_duration_ms','unfiltered_action_target_miss_count','unfiltered_hard_limit_breach_count','max_filtered_probe_duration_ms','filtered_probe_target_miss_count','filtered_probe_hard_limit_breach_count']},
  'per_peer_at_end':{'type':'array'},'system_ranging_at_end':{'type':'object'},'events':{'type':'array'},'geometry_at_end':{},'fused_range_observations_at_end':{'type':'array'}
 }
}
write('protocol/schemas/validation-run-snapshot-v4.json',json.dumps(schema,indent=2)+'\n')

# ---- Dev16 validator --------------------------------------------------------
validator=r'''#!/usr/bin/env python3
from __future__ import annotations
import json, sys
from collections import Counter,defaultdict
from pathlib import Path

BUILD='0.2.0-experimental.16'; SCHEMA=4; PROTOCOL=2
UNFILTERED_TARGET=9500; UNFILTERED_HARD=10000
PROBE_TARGET=14500; PROBE_HARD=15000
ROLLING_WINDOW=300000; ROLLING_LIMIT=3
class ContractError(Exception): pass
def req(o,k,p='$'):
    if not isinstance(o,dict) or k not in o: raise ContractError(f'MISSING_REQUIRED_FIELD:{p}.{k}')
    return o[k]
def req_int(o,k,p='$'):
    v=req(o,k,p)
    if type(v) is not int: raise ContractError(f'INVALID_TYPE_INT:{p}.{k}')
    return v
def req_num(o,k,p='$'):
    v=req(o,k,p)
    if type(v) not in (int,float): raise ContractError(f'INVALID_TYPE_NUMBER:{p}.{k}')
    return float(v)
def req_str(o,k,p='$'):
    v=req(o,k,p)
    if not isinstance(v,str) or not v: raise ContractError(f'INVALID_TYPE_STRING:{p}.{k}')
    return v
def req_bool(o,k,p='$'):
    v=req(o,k,p)
    if type(v) is not bool: raise ContractError(f'INVALID_TYPE_BOOL:{p}.{k}')
    return v
def req_dict(o,k,p='$'):
    v=req(o,k,p)
    if not isinstance(v,dict): raise ContractError(f'INVALID_TYPE_DICT:{p}.{k}')
    return v
def req_list(o,k,p='$'):
    v=req(o,k,p)
    if not isinstance(v,list): raise ContractError(f'INVALID_TYPE_LIST:{p}.{k}')
    return v

def recovery_analysis(run):
    errors=[]; warnings=[]; infos=[]; groups=defaultdict(list); requests=[]
    events=req_list(run,'events','$.validation_run')
    for i,e in enumerate(events):
        if not isinstance(e,dict): errors.append(f'INVALID_EVENT_TYPE:{i}'); continue
        try: typ=req_str(e,'type',f'$.validation_run.events[{i}]'); req_int(e,'seq',f'$.validation_run.events[{i}]'); req_num(e,'wall_ms',f'$.validation_run.events[{i}]')
        except ContractError as x: errors.append(str(x)); continue
        g=e.get('recovery_generation')
        if type(g) is int: groups[g].append(e)
        if typ=='RECOVERY_REQUESTED':
            if type(g) is not int: errors.append(f'MISSING_RECOVERY_GENERATION:{i}')
            else: requests.append(float(e['wall_ms']))
    totals=Counter(); peers=defaultdict(Counter); maxu=maxp=0
    for g,es in sorted(groups.items()):
        es=sorted(es,key=lambda e:e['seq']); r=[e for e in es if e['type']=='RECOVERY_REQUESTED']; f=[e for e in es if e['type']=='FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY']; ok=[e for e in es if e['type']=='RECOVERY_SUCCESS']; bad=[e for e in es if e['type']=='RECOVERY_FAILURE']; term=ok+bad
        if not (r or f or term): continue
        if len(r)!=1: errors.append(f'RECOVERY_REQUEST_COUNT_INVALID:g{g}'); continue
        if len(term)!=1: errors.append(f'RECOVERY_TERMINAL_COUNT_INVALID:g{g}'); continue
        d=float(term[0]['wall_ms'])-float(r[0]['wall_ms']); maxu=max(maxu,int(d))
        if d<0: errors.append(f'UNFILTERED_DURATION_INVALID:g{g}')
        elif d>UNFILTERED_HARD: errors.append(f'UNFILTERED_HARD_LIMIT_BREACHED:g{g}:{int(d)}')
        elif d>UNFILTERED_TARGET: warnings.append(f'UNFILTERED_ACTION_TARGET_MISSED:g{g}:{int(d)}')
        if ok:
            if len(f)!=1: errors.append(f'RECOVERY_FIRST_VALID_COUNT_INVALID:g{g}')
            elif not (r[0]['seq']<f[0]['seq']<ok[0]['seq']): errors.append(f'RECOVERY_CAUSAL_ORDER_INVALID:g{g}')
        elif f: errors.append(f'FIRST_VALID_WITH_FAILURE:g{g}')
        trig=r[0].get('trigger_kind'); target=r[0].get('trigger_peer_id') or r[0].get('peer_id')
        if trig=='PEER_STARVATION':
            totals['targeted_request']+=1
            if not isinstance(target,str) or not target: errors.append(f'RECOVERY_TARGET_MISSING:g{g}')
            else:
                peers[target]['request']+=1
                if f:
                    totals['first']+=1; peers[target]['first']+=1
                    if f[0].get('peer_id')!=target: errors.append(f'FIRST_VALID_WRONG_TARGET:g{g}')
                if ok:
                    totals['targeted_success']+=1; peers[target]['success']+=1
                    if ok[0].get('peer_id')!=target: errors.append(f'RECOVERY_SUCCESS_WRONG_TARGET:g{g}')
                if bad: totals['targeted_failure']+=1; peers[target]['failure']+=1
        elif f: totals['first']+=1
        ps=[e for e in es if e['type']=='ACQUISITION_STRATEGY_CHANGED' and e.get('to_strategy')=='FILTERED_RECOVERY_PROBE']
        pe=[e for e in es if e['type']=='ACQUISITION_STRATEGY_CHANGED' and e.get('from_strategy')=='FILTERED_RECOVERY_PROBE']
        if len(ps)!=1: errors.append(f'RECOVERY_PROBE_START_INVALID:g{g}')
        else:
            end=float(pe[0]['wall_ms']) if len(pe)==1 else req_num(run,'ended_wall_ms','$.validation_run')
            d=end-float(ps[0]['wall_ms']); maxp=max(maxp,int(d))
            if d<0: errors.append(f'FILTERED_PROBE_DURATION_INVALID:g{g}')
            elif d>PROBE_HARD: errors.append(f'FILTERED_PROBE_HARD_LIMIT_BREACHED:g{g}:{int(d)}')
            elif d>PROBE_TARGET: warnings.append(f'FILTERED_PROBE_EXIT_TARGET_MISSED:g{g}:{int(d)}')
    requests.sort(); roll=max((sum(1 for x in requests if t<=x<=t+ROLLING_WINDOW) for t in requests),default=0)
    if roll>ROLLING_LIMIT: errors.append(f'RECOVERY_BUDGET_EXCEEDED:{roll}')
    return {'errors':list(dict.fromkeys(errors)),'warnings':list(dict.fromkeys(warnings)),'informational':infos,'max_rolling':roll,'total_requests':len(requests),'max_unfiltered':maxu,'max_probe':maxp,'totals':totals,'peers':peers}

def validate_export(doc,acceptance=True,ignore_three_node=False):
    gates={f'G{i}':{'pass':True,'errors':[]} for i in range(17)}; warnings=[]; info=[]
    def fail(g,c): gates[g]['pass']=False; gates[g]['errors'].append(c) if c not in gates[g]['errors'] else None
    try: run=req_dict(doc,'validation_run')
    except ContractError as e: fail('G0',str(e)); return {'pass':False,'gates':gates,'warnings':warnings,'informational':info}
    try:
        if req_str(doc,'build')!=BUILD: fail('G0','BUILD_MISMATCH')
        if req_int(doc,'protocol_version')!=PROTOCOL: fail('G0','PROTOCOL_MISMATCH')
        if req_int(run,'snapshot_schema_version','$.validation_run')!=SCHEMA: fail('G0','SNAPSHOT_SCHEMA_DRIFT')
        if req_bool(run,'snapshot_frozen','$.validation_run') is not True: fail('G0','SNAPSHOT_NOT_FROZEN')
        if req_bool(doc,'json_self_contained') is not True or req_bool(doc,'screenshots_required') is not False: fail('G0','EVIDENCE_CONTRACT_DRIFT')
    except ContractError as e: fail('G0',str(e))
    try:
        pf=req_dict(run,'preflight_at_start','$.validation_run')
        if req_bool(pf,'ready','$.validation_run.preflight_at_start') is not True: fail('G2','PREFLIGHT_NOT_READY')
    except ContractError as e: fail('G2',str(e))
    try:
        if acceptance and req_num(run,'elapsed_ms','$.validation_run')<300000: fail('G3','LONG_RUN_INELIGIBLE')
    except ContractError as e: fail('G3',str(e))
    try:
        env=req_dict(run,'environment','$.validation_run')
        if req_bool(env,'valid','$.validation_run.environment') is not True: fail('G4','ENVIRONMENT_INVALID')
    except ContractError as e: fail('G4',str(e))
    try:
        acq=req_dict(run,'acquisition_state_at_end','$.validation_run')
        required={'recovery_unfiltered_hard_limit_ms':10000,'recovery_unfiltered_action_target_ms':9500,'filtered_probe_exit_target_ms':14500,'filtered_probe_hard_limit_ms':15000,'filtered_probe_action_target_ms':14000,'recovery_budget_window_ms':300000,'recovery_budget_limit':3}
        for k,v in required.items():
            if req_int(acq,k,'$.validation_run.acquisition_state_at_end')!=v: fail('G14',f'FROZEN_VALUE_DRIFT:{k}')
        req_int(acq,'recovery_attempt_delta_total','$.validation_run.acquisition_state_at_end'); req_int(acq,'recovery_attempts_in_current_5min_window_at_end','$.validation_run.acquisition_state_at_end'); frozen_roll=req_int(acq,'recovery_attempts_max_in_any_rolling_5min_window','$.validation_run.acquisition_state_at_end')
        if acceptance:
            if req_str(acq,'logical_acquisition_strategy','$.validation_run.acquisition_state_at_end')!='FILTERED_PRIMARY': fail('G5','LONG_END_NOT_FILTERED_PRIMARY')
            if req(acq,'active_recovery_generation','$.validation_run.acquisition_state_at_end') is not None: fail('G5','ACTIVE_RECOVERY_AT_LONG_END')
            if req(acq,'strategy_recovery_generation','$.validation_run.acquisition_state_at_end') is not None: fail('G5','STRATEGY_RECOVERY_AT_LONG_END')
    except ContractError as e: fail('G5',str(e)); fail('G14',str(e)); frozen_roll=None
    try:
        if acceptance and not ignore_three_node and req_num(run,'all_expected_peer_metric_uptime_percent','$.validation_run')<90: fail('G6','ALL_EXPECTED_PEER_METRIC_UPTIME_LOW')
        if acceptance and not ignore_three_node and req_num(run,'geometry_2d_uptime_percent','$.validation_run')<90: fail('G7','GEOMETRY2D_UPTIME_LOW')
    except ContractError as e: fail('G6',str(e)); fail('G7',str(e))
    try:
        c=req_dict(run,'validation_counters','$.validation_run')
        if req_int(c,'peer_expire_delta','$.validation_run.validation_counters')!=0: fail('G8','PEER_EXPIRE_NONZERO')
    except ContractError as e: fail('G8',str(e))
    try:
        ra=recovery_analysis(run); warnings+=ra['warnings']; info+=ra['informational']
        for e in ra['errors']:
            if 'BUDGET' in e: fail('G9',e)
            elif 'WRONG_TARGET' in e or 'TARGET_MISSING' in e: fail('G11',e)
            elif 'HARD_LIMIT' in e: fail('G13',e)
            else: fail('G10',e)
        if frozen_roll is not None and frozen_roll!=ra['max_rolling']: fail('G12',f'ROLLING_SUMMARY_EVENT_MISMATCH:{frozen_roll}!={ra["max_rolling"]}')
        ts=req_dict(run,'recovery_timing_summary','$.validation_run')
        checks={'max_unfiltered_duration_ms':ra['max_unfiltered'],'max_filtered_probe_duration_ms':ra['max_probe']}
        for k,v in checks.items():
            if req_int(ts,k,'$.validation_run.recovery_timing_summary')!=v: fail('G12',f'TIMING_SUMMARY_EVENT_MISMATCH:{k}')
        if req_int(ts,'unfiltered_hard_limit_breach_count','$.validation_run.recovery_timing_summary')!=0: fail('G13','UNFILTERED_HARD_BREACH_SUMMARY')
        if req_int(ts,'filtered_probe_hard_limit_breach_count','$.validation_run.recovery_timing_summary')!=0: fail('G13','FILTERED_PROBE_HARD_BREACH_SUMMARY')
    except ContractError as e: fail('G12',str(e)); fail('G13',str(e)); ra={'totals':Counter()}
    # G15 history and G16 campaign are aggregate validators, not single-export gates.
    ok=all(v['pass'] for v in gates.values())
    return {'pass':ok,'gates':gates,'warnings':list(dict.fromkeys(warnings)),'informational':list(dict.fromkeys(info)),'recovery':{k:v for k,v in ra.items() if k not in ('totals','peers')}}

def load_exports(d):
    out=[]
    for p in sorted(Path(d).glob('*.json')):
        try:
            x=json.load(open(p)); out.append((p,x))
        except Exception: pass
    return out

def validate_campaign(d,directed=False):
    rows=[]; targeted=0; bydev=defaultdict(dict)
    for p,x in load_exports(d):
        r=validate_export(x,acceptance=not (x.get('export_metadata',{}).get('snapshot_stage')=='SHORT'),ignore_three_node=directed)
        rows.append({'file':p.name,**r})
        md=x.get('export_metadata',{}); dev=md.get('device_alias') or md.get('device_model') or p.name; stage=md.get('snapshot_stage'); run=x.get('validation_run',{})
        if stage: bydev[dev][stage]=(x,run)
        for e in run.get('events',[]):
            if e.get('type')=='RECOVERY_SUCCESS' and e.get('trigger_kind')=='PEER_STARVATION': targeted+=1
    errors=[]
    if directed:
        if len(bydev)<2: errors.append('DIRECTED_REQUIRES_TWO_DEVICES')
        for dev,st in bydev.items():
            miss={'LONG_1','LONG_2','SHORT','LONG_POST_SHORT'}-set(st)
            if miss: errors.append(f'MISSING_STAGES:{dev}:{sorted(miss)}'); continue
            a=st['LONG_1'][1]; b=st['LONG_2'][1]; c=st['LONG_POST_SHORT'][1]; short=st['SHORT'][1]
            if not (a.get('run_id')==b.get('run_id')==c.get('run_id')): errors.append(f'HISTORY_RUN_ID_CHANGED:{dev}')
            def stable(j):
                z=dict(j); z.pop('snapshot_identity_sha256',None); return z
            if not (stable(a)==stable(b)==stable(c)): errors.append(f'HISTORY_SNAPSHOT_MUTATED:{dev}')
            if short.get('run_id')==a.get('run_id'): errors.append(f'SHORT_RUN_ID_REUSED:{dev}')
            if st['SHORT'][0].get('export_metadata',{}).get('source_long_run_id')!=a.get('run_id'): errors.append(f'SHORT_SOURCE_LONG_MISMATCH:{dev}')
        if targeted<1: errors.append('CAMPAIGN_TARGETED_PEER_STARVATION_REQUIRED')
    return {'pass':all(r['pass'] for r in rows) and not errors,'directed':directed,'targeted_recovery_success_count':targeted,'campaign_errors':errors,'results':rows}
'''
write('validation/analysis/dev16_validation.py',validator)
write('validation/analysis/validate_dev16_acceptance.py',"#!/usr/bin/env python3\nimport argparse,json\nfrom dev16_validation import validate_campaign\np=argparse.ArgumentParser(); p.add_argument('--evidence-dir',required=True); p.add_argument('--output',required=True); a=p.parse_args(); r=validate_campaign(a.evidence_dir,False); open(a.output,'w').write(json.dumps(r,indent=2)+'\\n'); raise SystemExit(0 if r['pass'] else 1)\n")
write('validation/analysis/validate_dev16_directed_smoke.py',"#!/usr/bin/env python3\nimport argparse,json\nfrom dev16_validation import validate_campaign\np=argparse.ArgumentParser(); p.add_argument('--evidence-dir',required=True); p.add_argument('--output',required=True); a=p.parse_args(); r=validate_campaign(a.evidence_dir,True); open(a.output,'w').write(json.dumps(r,indent=2)+'\\n'); raise SystemExit(0 if r['pass'] else 1)\n")
write('validation/analysis/build_dev16_acceptance_report.py',"#!/usr/bin/env python3\nimport argparse,json\nfrom dev16_validation import validate_campaign\np=argparse.ArgumentParser(); p.add_argument('--evidence-dir',required=True); p.add_argument('--output',required=True); p.add_argument('--directed',action='store_true'); a=p.parse_args(); r=validate_campaign(a.evidence_dir,a.directed); open(a.output,'w').write(json.dumps({'report_version':18,'release':'dev-16',**r},indent=2)+'\\n'); raise SystemExit(0 if r['pass'] else 1)\n")

# Boundary unit test does not fake Android scheduling; it freezes validator semantics.
test=r'''#!/usr/bin/env python3
import sys
sys.path.insert(0,'validation/analysis')
from dev16_validation import UNFILTERED_TARGET,UNFILTERED_HARD,PROBE_TARGET,PROBE_HARD,ROLLING_LIMIT
assert (UNFILTERED_TARGET,UNFILTERED_HARD)==(9500,10000)
assert (PROBE_TARGET,PROBE_HARD)==(14500,15000)
assert ROLLING_LIMIT==3
for d,fail,warn in [(9499,False,False),(9500,False,False),(9501,False,True),(9999,False,True),(10000,False,True),(10001,True,False),(10148,True,False)]:
    assert (d>UNFILTERED_HARD)==fail and ((UNFILTERED_TARGET<d<=UNFILTERED_HARD)==warn)
for d,fail,warn in [(14500,False,False),(14501,False,True),(14999,False,True),(15000,False,True),(15001,True,False)]:
    assert (d>PROBE_HARD)==fail and ((PROBE_TARGET<d<=PROBE_HARD)==warn)
print('DEV16_TOOLING_BOUNDARIES_PASS')
'''
write('validation/analysis/test_dev16_tooling.py',test)

# ---- contracts/docs ---------------------------------------------------------
evidence={'schema':'dev16-self-contained-json-evidence-v4','snapshot_schema_version':4,'report_version':18,'protocol_version':2,'screenshots_required':False,'json_self_contained':True,'acceptance_source':'validation_run frozen snapshot','runtime_live_preflight_not_acceptance_evidence':True}
gates={'release':'dev-16','G0':'version/schema','G1':'frozen physical truth','G2':'preflight','G3':'duration','G4':'environment','G5':'completed acquisition state','G6':'3-node usable metric continuity','G7':'3-node geometry 2D','G8':'peer expiry','G9':'rolling recovery budget','G10':'recovery causality','G11':'target peer','G12':'counters/events/frozen summaries','G13':'hard recovery timing','G14':'evidence contract','G15':'history isolation','G16':'directed campaign semantics'}
write('validation/contracts/dev16-evidence-contract.json',json.dumps(evidence,indent=2)+'\n'); write('validation/contracts/dev16-gates.json',json.dumps(gates,indent=2)+'\n')
frozen='''# DEV16_FROZEN_TRUTH\n\nRelease `dev-16`; build `0.2.0-experimental.16`; report 18; protocol 2; snapshot v4.\n\nFrozen physical truth: `android-ble-lab-v1`, RSSI@1m -69.19 dBm, n=3.62, valid 0.5–5.0 m, min samples 3, fresh 5000 ms, holdover/hard expiry 10000 ms, unfiltered hard 10000/action 9500 ms, probe observed target 14500/action 14000/hard 15000 ms, cooldown 30000 ms, recovery budget 3/rolling 300000 ms, system ranging BLE yield 120000 ms. Manual geometry=false; automatic geometry=true; human scanning/localization/rescue validated=false; screenshots=false.\n\nDo not change estimator, calibration, sigma aging, holdover, reciprocal fusion, graph/fused range, autogeometry, coordinator publication, API36 coexistence/yield or UDP protocol in dev16.\n'''
write('DEV16_FROZEN_TRUTH.md',frozen)
doc='''# TESTING_DEV16\n\n## 1. Verify/install\nVerify `BodyFinder-dev16-universal.apk` against `SHA256SUMS.txt`, then install the same APK on Pixel 10 Pro and Pixel 7 Pro. Keep Bluetooth ON, permissions granted, Battery Saver OFF, screen ON, app foreground and field service RUNNING. No screenshots are required.\n\n## 2. Directed smoke (2 phones)\nOn each phone: run LONG >=330 s -> export `LONG_1`; export the same run again as `LONG_2`; start SHORT immediately for 45–75 s -> export `SHORT`; reselect original LONG -> export `LONG_POST_SHORT`. Total: 8 JSON. Across the campaign provoke >=1 complete `PEER_STARVATION` targeted recovery (only one phone is sufficient).\n\nPut the 8 JSON in `evidence-directed/` and run:\n```bash\nunzip validators-dev16.zip -d validators-dev16\npython3 validators-dev16/validate_dev16_directed_smoke.py --evidence-dir evidence-directed --output directed_smoke_report.json\n```\nPASS requires no unfiltered >10000 ms, no probe >15000 ms, rolling max <=3, each LONG ends FILTERED_PRIMARY with no active recovery, event/counter/summaries consistent, immutable LONG history, immediate LONG->SHORT and valid environment. Target misses within hard limits are warnings.\n\n## 3. Three-device continuity\nPixel 10 Pro + Pixel 7 Pro + Lenovo TB-J606L: one simultaneous LONG >=330 s; export one LONG JSON per device into `evidence-3node/`. Run:\n```bash\npython3 validators-dev16/validate_dev16_acceptance.py --evidence-dir evidence-3node --output acceptance_report.json\n```\nExpected: two remote peers, all-expected-peer metric uptime >=90%, geometry 2D >=90%, peer_expire_delta=0, environment valid, rolling budget <=3 and hard deadlines PASS. Accuracy/recalibration and screenshots are not required.\n\nAfter hardware PASS, share the 8 directed JSON + 3 three-node JSON + both generated reports. CI intentionally leaves `final_go=false` until this physical evidence exists.\n'''
write('docs/TESTING_DEV16.md',doc)
write('RELEASE_DEV16_TRIGGER.txt','dev-16 release trigger generated by apply_dev16_contract_hardening.py\n')
print('DEV16_CONTRACT_HARDENING_MATERIALIZED')
