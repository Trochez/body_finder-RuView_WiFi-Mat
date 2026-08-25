#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def r(p): return (ROOT/p).read_text(encoding='utf-8')
def w(p,s): (ROOT/p).write_text(s,encoding='utf-8')
def one(s,a,b,label):
    if a not in s: raise SystemExit(f'missing {label}')
    return s.replace(a,b,1)

# Fix/extend event log independently of its dev11 signature.
p='apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/ValidationEventLog.kt'; s=r(p)
if 'val peerId: String?' not in s:
    s=one(s,'  val recoveryGeneration: Long?,\n)','  val recoveryGeneration: Long?,\n  val peerId: String?,\n  val triggerKind: String?,\n)','event fields')
if 'triggerKind: String? = null' not in s:
    s=one(s,'fun record(type: String, reason: String = "", now: Long = System.currentTimeMillis()) {','fun record(type: String, reason: String = "", now: Long = System.currentTimeMillis(), peerId: String? = null, recoveryGeneration: Long? = null, triggerKind: String? = null) {','event signature')
if 'val generation = recoveryGeneration ?: BleAcquisitionPolicy.activeRecoveryGeneration()' not in s:
    s=s.replace('val generation = BleAcquisitionPolicy.activeRecoveryGeneration()','val generation = recoveryGeneration ?: BleAcquisitionPolicy.activeRecoveryGeneration()',1)
if 'rs, y, generation, peerId, triggerKind' not in s:
    s=s.replace('rs, y, generation,\n      )','rs, y, generation, peerId, triggerKind,\n      )',1)
if '.put("peer_id", e.peerId' not in s:
    s=s.replace('.put("recovery_generation", e.recoveryGeneration ?: JSONObject.NULL)', '.put("recovery_generation", e.recoveryGeneration ?: JSONObject.NULL)\n          .put("peer_id", e.peerId ?: JSONObject.NULL)\n          .put("trigger_kind", e.triggerKind ?: JSONObject.NULL)',1)
w(p,s)

# Add per-peer snapshot counters API.
p='apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/PeerStarvationRecovery.kt'; s=r(p)
if 'fun peerCounters(peerId:String)' not in s:
    s=s.replace('  fun counters()=longArrayOf(candidateCount.get(),starvationCount.get(),requestCount.get(),successCount.get(),failureCount.get())','  fun counters()=longArrayOf(candidateCount.get(),starvationCount.get(),requestCount.get(),successCount.get(),failureCount.get())\n  fun peerCounters(peerId:String):LongArray { val x=runtime(peerId); return longArrayOf(x.starvationCount,x.recoveryParticipationCount,x.recoverySuccessCount,x.recoveryFailureCount) }',1)
w(p,s)

p='apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt'; s=r(p)
# Global validation baselines/deltas.
if 'baselinePeerStarvation' not in s:
    s=s.replace('  @Volatile private var baselineRecoveryAttempts: Long = 0','  @Volatile private var baselineRecoveryAttempts: Long = 0\n  @Volatile private var baselinePeerStarvation: Long = 0\n  @Volatile private var baselinePeerStarvationRequests: Long = 0\n  @Volatile private var baselinePeerStarvationSuccesses: Long = 0\n  @Volatile private var baselinePeerStarvationFailures: Long = 0',1)
    s=s.replace('    baselineRecoveryAttempts = BleAcquisitionPolicy.recoveryAttemptCount()','    baselineRecoveryAttempts = BleAcquisitionPolicy.recoveryAttemptCount()\n    val ps=PeerStarvationRecovery.counters()\n    baselinePeerStarvation=ps[1]; baselinePeerStarvationRequests=ps[2]; baselinePeerStarvationSuccesses=ps[3]; baselinePeerStarvationFailures=ps[4]',1)
    s=s.replace('.put("recovery_attempt_delta", (BleAcquisitionPolicy.recoveryAttemptCount() - baselineRecoveryAttempts).coerceAtLeast(0))', '.put("recovery_attempt_delta", (BleAcquisitionPolicy.recoveryAttemptCount() - baselineRecoveryAttempts).coerceAtLeast(0))\n      .put("peer_starvation_delta", (PeerStarvationRecovery.counters()[1]-baselinePeerStarvation).coerceAtLeast(0))\n      .put("peer_starvation_recovery_request_delta", (PeerStarvationRecovery.counters()[2]-baselinePeerStarvationRequests).coerceAtLeast(0))\n      .put("peer_starvation_recovery_success_delta", (PeerStarvationRecovery.counters()[3]-baselinePeerStarvationSuccesses).coerceAtLeast(0))\n      .put("peer_starvation_recovery_failure_delta", (PeerStarvationRecovery.counters()[4]-baselinePeerStarvationFailures).coerceAtLeast(0))',1)
    s=s.replace('.put("cohort_stall_delta", base.optLong("cohort_stall_delta"))', '.put("cohort_stall_delta", base.optLong("cohort_stall_delta"))\n      .put("peer_starvation_delta", base.optLong("peer_starvation_delta"))\n      .put("peer_starvation_recovery_request_delta", base.optLong("peer_starvation_recovery_request_delta"))\n      .put("peer_starvation_recovery_success_delta", base.optLong("peer_starvation_recovery_success_delta"))\n      .put("peer_starvation_recovery_failure_delta", base.optLong("peer_starvation_recovery_failure_delta"))',1)

# Per-peer run baselines.
if 'validationStarvationBaselineByPeer' not in s:
    s=s.replace('  val validationAcquisitionBaselineByIdentity = ConcurrentHashMap<String, BleAcquisitionCounterSnapshot>()','  val validationAcquisitionBaselineByIdentity = ConcurrentHashMap<String, BleAcquisitionCounterSnapshot>()\n  val validationStarvationBaselineByPeer = ConcurrentHashMap<String, LongArray>()',1)
    s=s.replace('    validationAcquisitionBaselineByIdentity.clear()\n    acquisitionStatsByIdentity.forEach', '    validationAcquisitionBaselineByIdentity.clear()\n    validationStarvationBaselineByPeer.clear()\n    peers.values.forEach { pair -> try { val id=JSONObject(pair.first).optString("node_id"); if(id.isNotBlank()) validationStarvationBaselineByPeer[id]=PeerStarvationRecovery.peerCounters(id) } catch(_:Throwable){} }\n    acquisitionStatsByIdentity.forEach',1)
    s=s.replace('    validationAcquisitionBaselineByIdentity.clear()\n    invalidRssiEventsByIdentity.clear()', '    validationAcquisitionBaselineByIdentity.clear()\n    validationStarvationBaselineByPeer.clear()\n    invalidRssiEventsByIdentity.clear()',1)

# Merge explicit starvation diagnostics into every peer object.
if 'run_starvation_count' not in s:
    target='''          put("acquisition", acquisitionStats?.diagnostics(now, validFresh.size, validRetained.size, effectiveBaseline) ?: JSONObject.NULL)'''
    repl='''          put("acquisition", acquisitionStats?.diagnostics(now, validFresh.size, validRetained.size, effectiveBaseline) ?: JSONObject.NULL)\n          val starvation=PeerStarvationRecovery.diagnostics(peerId)\n          val ps=PeerStarvationRecovery.peerCounters(peerId); val pb=FabricRuntime.validationStarvationBaselineByPeer[peerId] ?: longArrayOf(0,0,0,0)\n          put("peer_health_state",starvation.optString("peer_health_state"))\n          put("starvation_candidate_since_wall_ms",starvation.opt("starvation_candidate_since_wall_ms"))\n          put("starvation_since_wall_ms",starvation.opt("starvation_since_wall_ms"))\n          put("starvation_count",ps[0])\n          put("starvation_recovery_participation_count",ps[1])\n          put("last_starvation_recovery_generation",starvation.opt("last_starvation_recovery_generation"))\n          put("last_starvation_recovery_latency_ms",starvation.opt("last_starvation_recovery_latency_ms"))\n          put("run_starvation_count",(ps[0]-pb[0]).coerceAtLeast(0))\n          put("run_starvation_recovery_participation_count",(ps[1]-pb[1]).coerceAtLeast(0))\n          put("run_starvation_recovery_success_count",(ps[2]-pb[2]).coerceAtLeast(0))\n          put("run_starvation_recovery_failure_count",(ps[3]-pb[3]).coerceAtLeast(0))'''
    s=one(s,target,repl,'per-peer telemetry')

# JSON-only evidence: preflight, device, build, safety and frozen physical truth at root.
if 'private fun preflightDiagnostics' not in s:
    anchor='''  private fun validationRunDiagnostics(ctx: Context, now: Long = System.currentTimeMillis()): JSONObject {'''
    helper='''  private fun preflightDiagnostics(ctx:Context,now:Long):JSONObject {\n    val issues=validationEnvironmentIssues(ctx)\n    val manager=ctx.getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager\n    val expected=expectedKnownPeerCount()\n    return JSONObject()\n      .put("valid",issues.isEmpty() && expected>=2 && BleAcquisitionPolicy.currentStrategy()==BleAcquisitionStrategy.FILTERED_PRIMARY)\n      .put("bluetooth_on",manager?.adapter?.isEnabled==true)\n      .put("battery_saver_off",(ctx.getSystemService(Context.POWER_SERVICE) as? PowerManager)?.isPowerSaveMode!=true)\n      .put("screen_on",(ctx.getSystemService(Context.POWER_SERVICE) as? PowerManager)?.isInteractive==true)\n      .put("app_foreground",ValidationRuntime.appVisibility=="active")\n      .put("foreground_service_running",FieldServiceState.state=="RUNNING")\n      .put("expected_ble_peer_count",expected)\n      .put("logical_strategy",BleAcquisitionPolicy.currentStrategy().name)\n      .put("scan_filter_mode","MANUFACTURER_FILTERED")\n      .put("hardware_filter_count",if(BleAcquisitionPolicy.currentStrategy()==BleAcquisitionStrategy.UNFILTERED_RECOVERY) 0 else 1)\n      .put("location_service_enabled",locationServiceEnabled(ctx) ?: JSONObject.NULL)\n      .put("issues",JSONArray(issues))\n  }\n\n  private fun validationRunDiagnostics(ctx: Context, now: Long = System.currentTimeMillis()): JSONObject {'''
    s=one(s,anchor,helper,'preflight helper')
if '.put("release_truth"' not in s:
    old='''    return JSONObject()\n      .put("ble_diagnostics", bleDiagnostics(ctx, now))'''
    new='''    return JSONObject()\n      .put("schema_version",14)\n      .put("release","dev-12")\n      .put("build","0.2.0-experimental.12")\n      .put("protocol_version",2)\n      .put("device",deviceReport(ctx))\n      .put("preflight",preflightDiagnostics(ctx,now))\n      .put("release_truth",JSONObject()\n        .put("profile_id","android-ble-lab-v1").put("rssi_at_1m_dbm",-69.19).put("path_loss_exponent",3.62)\n        .put("min_samples_for_range",3).put("fresh_ms",5000).put("holdover_max_ms",10000).put("hard_expiry_ms",10000)\n        .put("valid_distance_min_m",0.5).put("valid_distance_max_m",5.0).put("primary_acquisition","FILTERED_PRIMARY")\n        .put("recovery_acquisition","UNFILTERED_RECOVERY").put("restart_cooldown_ms",30000).put("max_recoveries_per_5min",3)\n        .put("physical_confidence","COARSE"))\n      .put("safety_truth",JSONObject().put("human_scanning_enabled",false).put("human_localization_validated",false).put("rescue_use_validated",false))\n      .put("ble_diagnostics", bleDiagnostics(ctx, now))'''
    s=one(s,old,new,'root diagnostic truth')

# Ensure screen flag releases when fabric stops too.
if 'keepValidationScreenAwake(false)\n      FabricRuntime.stop()' not in s:
    s=s.replace('      FabricRuntime.stop()\n      true\n    }\n    Function("getPeersJson")','      keepValidationScreenAwake(false)\n      FabricRuntime.stop()\n      true\n    }\n    Function("getPeersJson")',1)
w(p,s)
print('dev12 fixup complete')
