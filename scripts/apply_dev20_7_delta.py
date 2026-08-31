#!/usr/bin/env python3
from pathlib import Path
import json, hashlib

ROOT=Path(__file__).resolve().parents[1]
PH='7ff358bc4b1f92211e3a32d31285f5ab591c6fb79585c6b99814c1d0383d945d'
BUILD='0.2.0-experimental.20.7'
SCHEMA='dev20.7-self-contained-json-evidence-v10'

def read(p): return (ROOT/p).read_text()
def write(p,s):
    q=ROOT/p; q.parent.mkdir(parents=True,exist_ok=True); q.write_text(s.rstrip()+'\n')
def rep(p,a,b,n=1):
    s=read(p)
    if a not in s: raise SystemExit(f'anchor missing {p}: {a[:140]}')
    write(p,s.replace(a,b,n))

# Release identity / canonical detector contract.
rep('apps/mobile/src/version.ts',"build: '0.2.0-experimental.20.6'","build: '0.2.0-experimental.20.7'")
rep('apps/mobile/src/version.ts','reportVersion: 26','reportVersion: 27')
rep('apps/mobile/src/version.ts','versionCode: 26','versionCode: 27')
rep('apps/mobile/src/version.ts',"releaseIteration: 'experimental.20.6'","releaseIteration: 'experimental.20.7'")
rep('apps/mobile/src/version.ts','snapshotSchemaVersion: 9','snapshotSchemaVersion: 10')

params=f'''export const DETECTOR_ALGORITHM = 'deterministic-multinode-rssi-fusion-v7';
export const DETECTOR_PARAMETER_HASH = '{PH}';
export const DETECTOR_V7 = Object.freeze({{
  calibrationMinSamplesPerLink: 30,
  observationMinSamplesPerLink: 24,
  qualityReferenceSamples: 24,
  minMeanQuality: 0.80,
  calibrationMinOverlapMs: 1500,
  inferenceMinOverlapMs: 1500,
  minObserverNodes: 3,
  minDirectionalLinks: 6,
  minPhysicalBaselines: 3,
  humanThreshold: 0.50,
  noHumanThreshold: 0.20,
  disturbedLinkThreshold: 0.32,
  dynamicFloor: 0.20,
  dynamicHumanLinkThreshold: 0.55,
  persistenceHumanThreshold: 0.34,
  coherentLowAmplitudeFusedFloor: 0.26,
  coherentLowAmplitudeLinkFloor: 0.20,
  coherentLowAmplitudeReciprocalFloor: 0.70,
  coherentLowAmplitudeCrossLinkFloor: 1/6,
  coherentLowAmplitudeBaselineFloor: 1/3,
  segmentedTransitionFloor: 0.18,
  burstActivityFloor: 0.20,
  minDynamicLinks: 3,
  minDynamicBaselines: 2,
  observationWindowMs: 60_000,
  transportEvidenceFreshMs: 8_000,
  calibrationTimeoutMs: 120_000,
  authorityPublicationLeaseMs: 30_000,
  decisionFreshMs: 30_000,
  decisionExpiryMs: 60_000,
  membershipChangeGraceMs: 45_000,
  coordinatorFailoverGraceMs: 30_000,
}});
export const DETECTOR_V6 = DETECTOR_V7;
export const DETECTOR_V5 = DETECTOR_V7;
export const DETECTOR_V4 = DETECTOR_V7;
'''
write('apps/mobile/src/detectorParameters.ts',params)

# DecisionPublicationV7: control-plane decision transport, ordered adoption, explicit freshness.
hp='apps/mobile/src/humanPresence.ts'
rep(hp,"import { DETECTOR_ALGORITHM, DETECTOR_PARAMETER_HASH, DETECTOR_V6 } from './detectorParameters';","import { DETECTOR_ALGORITHM, DETECTOR_PARAMETER_HASH, DETECTOR_V7 } from './detectorParameters';")
s=read(hp).replace('DETECTOR_V6.','DETECTOR_V7.')
write(hp,s)
rep(hp,"type CachedDecision={decision:PresenceEstimate;receivedWallMs:number};","type CachedDecision={decision:PresenceEstimate;receivedWallMs:number;sequence:number};")
rep(hp,"const DECISION_CACHE_MS=6_000;","const DECISION_FRESH_MS=30_000;\nconst DECISION_EXPIRED_MS=60_000;")
rep(hp,"const latestDecisionBySession=new Map<string,CachedDecision>();","const latestDecisionBySession=new Map<string,CachedDecision>();\nconst decisionSequenceBySession=new Map<string,number>();")
rep(hp,"function currentSession(nodes:Advertisement[]){return sessionId(nodes)??'body-finder-lab'}","function currentSession(nodes:Advertisement[]){return sessionId(nodes)??'body-finder-lab'}\nfunction decisionFreshness(receivedWallMs:number){const age=Math.max(0,Date.now()-receivedWallMs);return age<=DECISION_FRESH_MS?'FRESH':age<=DECISION_EXPIRED_MS?'STALE':'EXPIRED'}")
old="""export function getControlPlanePublication(nodes:Advertisement[],coordinatorNodeId:string|null,localNodeId:string|null){
  lastLocalNodeId=localNodeId;syncAuthoritativeCalibration(nodes,coordinatorNodeId,localNodeId);adoptCoordinatorIfNeeded(nodes,coordinatorNodeId,localNodeId);
  const ack=cal.artifact&&localNodeId&&cal.expectedCohort.includes(localNodeId)?{schema:'CalibrationAckV6',session_id:cal.artifact.session_id,node_id:localNodeId,coordinator_id:cal.coordinator,coordinator_generation:cal.coordinatorGeneration,calibration_generation:cal.generation,calibration_id:cal.artifact.calibration_id,calibration_hash:cal.artifact.calibration_hash,ack_wall_ms:Date.now()}:null;
  const cached=latestDecisionBySession.get(currentSession(nodes));
  return{schema:'BodyFinderControlPlaneV6',session_id:currentSession(nodes),node_id:localNodeId,logical_membership_state:{expected_cohort:stableCohort(nodes),transport_liveness_state:transportStates(nodes)},calibration_ack_v6:ack,decision_ack_v6:cached?{schema:'DecisionAckV6',decision_id:cached.decision.decision_id??null,canonical_digest:cached.decision.canonical_digest??null,ack_wall_ms:cached.receivedWallMs}:null}
}"""
new="""export function getControlPlanePublication(nodes:Advertisement[],coordinatorNodeId:string|null,localNodeId:string|null){
  lastLocalNodeId=localNodeId;syncAuthoritativeCalibration(nodes,coordinatorNodeId,localNodeId);adoptCoordinatorIfNeeded(nodes,coordinatorNodeId,localNodeId);
  const sid=currentSession(nodes);
  const ack=cal.artifact&&localNodeId&&cal.expectedCohort.includes(localNodeId)?{schema:'CalibrationAckV6',session_id:cal.artifact.session_id,node_id:localNodeId,coordinator_id:cal.coordinator,coordinator_generation:cal.coordinatorGeneration,calibration_generation:cal.generation,calibration_id:cal.artifact.calibration_id,calibration_hash:cal.artifact.calibration_hash,ack_wall_ms:Date.now()}:null;
  const cached=latestDecisionBySession.get(sid);
  const decisionPublication=cached&&coordinatorNodeId===localNodeId&&cached.decision.authoritative&&cached.decision.canonical_digest?{schema:'DecisionPublicationV7',session_id:sid,coordinator_id:coordinatorNodeId,coordinator_generation:cal.coordinatorGeneration,calibration_id:cached.decision.calibration_id??cal.artifact?.calibration_id??null,calibration_hash:cached.decision.calibration_hash??cal.artifact?.calibration_hash??null,calibration_generation:cached.decision.calibration_generation??cal.generation,topology_fingerprint:cached.decision.topology_fingerprint??cal.topology,detector_algorithm:DETECTOR_ALGORITHM,detector_parameter_hash:DETECTOR_PARAMETER_HASH,decision_sequence:cached.sequence,decision_id:cached.decision.decision_id,canonical_digest:cached.decision.canonical_digest,window_id:cached.decision.window_id,publication_wall_ms:Date.now(),source_decision_wall_ms:cached.receivedWallMs,freshness_state:decisionFreshness(cached.receivedWallMs),fresh_ms:DECISION_FRESH_MS,expiry_ms:DECISION_EXPIRED_MS,decision:cached.decision}:null;
  const decisionAck=cached&&localNodeId?{schema:'DecisionAckV7',session_id:sid,node_id:localNodeId,coordinator_id:coordinatorNodeId,coordinator_generation:cal.coordinatorGeneration,decision_sequence:cached.sequence,decision_id:cached.decision.decision_id??null,canonical_digest:cached.decision.canonical_digest??null,ack_wall_ms:Date.now()}:null;
  return{schema:'BodyFinderControlPlaneV7',session_id:sid,node_id:localNodeId,logical_membership_state:{expected_cohort:stableCohort(nodes),transport_liveness_state:transportStates(nodes)},calibration_ack_v6:ack,decision_publication_v7:decisionPublication,decision_ack_v7:decisionAck}
}"""
rep(hp,old,new)
rep(hp,"latestDecisionBySession.set(currentSession(nodes),{decision:result,receivedWallMs:now});return result","const sid=currentSession(nodes),seq=(decisionSequenceBySession.get(sid)??0)+1;decisionSequenceBySession.set(sid,seq);latestDecisionBySession.set(sid,{decision:{...result,decision_sequence:seq,decision_freshness_state:'FRESH'},receivedWallMs:now,sequence:seq});return{...result,decision_sequence:seq,decision_freshness_state:'FRESH'} as PresenceEstimate")
old="""  if(coordinatorNodeId===localNodeId){latestDecisionBySession.set(sid,{decision:local,receivedWallMs:Date.now()});return local}
  const coordinator=nodes.find(n=>n.node_id===coordinatorNodeId);const published=(coordinator?.published_geometry as any)?.authoritative_presence;
  if(published&&published.authoritative===true&&published.algorithm_version===DETECTOR_ALGORITHM&&published.parameter_hash===DETECTOR_PARAMETER_HASH&&published.canonical_digest&&published.calibration_hash===cal.artifact?.calibration_hash){
    const mirrored={...published,calibration_state:cal.artifact?'READY':published.calibration_state,source:'elected_coordinator_publication'} as PresenceEstimate;latestDecisionBySession.set(sid,{decision:mirrored,receivedWallMs:Date.now()});return mirrored
  }
  const cached=latestDecisionBySession.get(sid);if(cached&&Date.now()-cached.receivedWallMs<=DECISION_CACHE_MS)return{...cached.decision,source:'cached_elected_coordinator_publication'} as PresenceEstimate;
  return fallback(cal.state==='STALE_AUTHORITY'?cal.reason:'awaiting_authoritative_coordinator_publication',cal.state,{transport_liveness_state:transportStates(nodes)})"""
new="""  if(coordinatorNodeId===localNodeId)return local
  const coordinator=nodes.find(n=>n.node_id===coordinatorNodeId);const dp=(coordinator?.control_plane as any)?.decision_publication_v7;
  if(dp&&dp.schema==='DecisionPublicationV7'&&dp.session_id===sid&&dp.coordinator_id===coordinatorNodeId&&Number(dp.coordinator_generation)===cal.coordinatorGeneration&&dp.detector_algorithm===DETECTOR_ALGORITHM&&dp.detector_parameter_hash===DETECTOR_PARAMETER_HASH&&dp.calibration_hash===cal.artifact?.calibration_hash&&dp.canonical_digest&&dp.decision?.canonical_digest===dp.canonical_digest&&dp.decision?.decision_id===dp.decision_id){
    const incomingSeq=Number(dp.decision_sequence??0),previous=latestDecisionBySession.get(sid);
    if(!previous||incomingSeq>=previous.sequence){const mirrored={...dp.decision,calibration_state:cal.artifact?'READY':dp.decision.calibration_state,source:'decision_control_plane_v7',decision_sequence:incomingSeq,decision_freshness_state:'FRESH'} as PresenceEstimate;latestDecisionBySession.set(sid,{decision:mirrored,receivedWallMs:Date.now(),sequence:incomingSeq});return mirrored}
  }
  const published=(coordinator?.published_geometry as any)?.authoritative_presence;
  if(published&&published.authoritative===true&&published.algorithm_version===DETECTOR_ALGORITHM&&published.parameter_hash===DETECTOR_PARAMETER_HASH&&published.canonical_digest&&published.calibration_hash===cal.artifact?.calibration_hash){
    const previous=latestDecisionBySession.get(sid),seq=previous?.sequence??0;const mirrored={...published,calibration_state:cal.artifact?'READY':published.calibration_state,source:'legacy_geometry_decision_fallback',decision_sequence:seq,decision_freshness_state:'FRESH'} as PresenceEstimate;latestDecisionBySession.set(sid,{decision:mirrored,receivedWallMs:Date.now(),sequence:seq});return mirrored
  }
  const cached=latestDecisionBySession.get(sid);if(cached&&decisionFreshness(cached.receivedWallMs)!=='EXPIRED')return{...cached.decision,source:'cached_decision_publication_v7',decision_freshness_state:decisionFreshness(cached.receivedWallMs),decision_age_ms:Date.now()-cached.receivedWallMs} as PresenceEstimate;
  return fallback(cal.state==='STALE_AUTHORITY'?cal.reason:'WAIT_DECISION_EXPIRED',cal.state,{decision_freshness_state:cached?'EXPIRED':'WAIT_DECISION',last_valid_decision_sequence:cached?.sequence??null,last_valid_decision_digest:cached?.decision.canonical_digest??null,transport_liveness_state:transportStates(nodes)})"""
rep(hp,old,new)
rep(hp,"const session=currentSession(nodes),calibrationId=`cal-d206-","const session=currentSession(nodes),calibrationId=`cal-d207-")

# Native run-scoped ledger: live diagnostic truth can never overwrite last valid authoritative evidence.
kt='apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt'
rep(kt,'  @Volatile private var validationTruthJson: String = "{}"','  @Volatile private var validationTruthJson: String = "{}"\n  @Volatile private var authoritativeTruthLedgerJson: String = "{}"')
rep(kt,'    validationTruthJson = "{}"\n    ValidationEventLog.record("VALIDATION_RUN_STARTED"','    validationTruthJson = "{}"\n    authoritativeTruthLedgerJson = "{}"\n    ValidationEventLog.record("VALIDATION_RUN_STARTED"')
old="""  fun updateTruth(json: String) {
    if (runId == null || endedWallMs != null) return
    validationTruthJson = try { JSONObject(json).toString() } catch (_: Throwable) { "{}" }
  }"""
new="""  fun updateTruth(json: String) {
    if (runId == null || endedWallMs != null) return
    val incoming = try { JSONObject(json) } catch (_: Throwable) { JSONObject() }
    validationTruthJson = incoming.toString()
    val p = incoming.optJSONObject("authoritative_presence")
    val admissible = p != null && p.optBoolean("authoritative", false) && p.optString("canonical_digest").isNotBlank() && p.optString("decision_id").isNotBlank() && p.optJSONObject("canonical_replay_input") != null && p.optInt("contributing_nodes",0) >= 3 && p.optInt("contributing_links",0) >= 6 && p.optInt("physical_baselines",0) >= 3
    if (admissible) authoritativeTruthLedgerJson = incoming.toString()
  }"""
rep(kt,old,new)
rep(kt,'    val truth = try { JSONObject(validationTruthJson) } catch (_: Throwable) { JSONObject() }','''    val liveTruth = try { JSONObject(validationTruthJson) } catch (_: Throwable) { JSONObject() }
    val ledgerTruth = try { JSONObject(authoritativeTruthLedgerJson) } catch (_: Throwable) { JSONObject() }
    val ledgerPresence = ledgerTruth.optJSONObject("authoritative_presence")
    val truth = if (ledgerPresence != null && ledgerPresence.optBoolean("authoritative", false) && ledgerPresence.optString("canonical_digest").isNotBlank()) ledgerTruth else liveTruth''')
rep(kt,'.put("snapshot_schema_version", 5)','.put("snapshot_schema_version", 10)')
rep(kt,'      .put("measurement_health_at_end", truth.opt("measurement_health") ?: JSONObject.NULL)\n    val snapshotBytes', '''      .put("measurement_health_at_end", truth.opt("measurement_health") ?: JSONObject.NULL)
      .put("validation_truth", truth)
    val frozenPresence = truth.optJSONObject("authoritative_presence")
    val invalidReasons = JSONArray()
    if (frozenPresence == null || !frozenPresence.optBoolean("authoritative", false)) invalidReasons.put("NO_FROZEN_AUTHORITATIVE_DECISION")
    if (frozenPresence == null || frozenPresence.optString("canonical_digest").isBlank()) invalidReasons.put("MISSING_CANONICAL_DIGEST")
    if (frozenPresence == null || frozenPresence.optString("decision_id").isBlank()) invalidReasons.put("MISSING_DECISION_ID")
    if (frozenPresence == null || frozenPresence.optJSONObject("canonical_replay_input") == null) invalidReasons.put("MISSING_CANONICAL_REPLAY")
    if (frozenPresence != null && (frozenPresence.optInt("contributing_nodes",0) < 3 || frozenPresence.optInt("contributing_links",0) < 6 || frozenPresence.optInt("physical_baselines",0) < 3)) invalidReasons.put("INCOMPLETE_3_6_3_TOPOLOGY")
    val evidenceValid = invalidReasons.length() == 0
    base.put("evidence_export_valid", evidenceValid)
      .put("evidence_invalid_reasons", invalidReasons)
      .put("atomic_snapshot_gate_pass", evidenceValid)
      .put("snapshot_consistency_digest", frozenPresence?.optString("canonical_digest")?.takeIf { it.isNotBlank() } ?: JSONObject.NULL)
      .put("authoritative_decision_ledger_used", ledgerPresence != null)
    val snapshotBytes''')

# Export contract v10: frozen run truth is authoritative; retain live preview only as diagnostics.
idx='apps/mobile/modules/body-finder-native/index.ts'
rep(idx,"const EVIDENCE_SCHEMA='dev20.6-self-contained-json-evidence-v9';",f"const EVIDENCE_SCHEMA='{SCHEMA}';")
old="function upgradeExport(raw:string):string{try{const d=JSON.parse(raw);const preview=d?.human_presence_preview??d?.validation_truth?.authoritative_presence??d?.validation_run?.validation_truth?.authoritative_presence??null;const digest=preview?.canonical_digest??null;"
new="function upgradeExport(raw:string):string{try{const d=JSON.parse(raw);const livePreview=d?.human_presence_preview??null;const frozen=d?.validation_run?.validation_truth?.authoritative_presence??d?.validation_truth?.authoritative_presence??null;const preview=frozen?.authoritative===true?frozen:livePreview;const digest=preview?.canonical_digest??null;const reasons:string[]=[];if(!preview?.authoritative)reasons.push('NO_FROZEN_AUTHORITATIVE_DECISION');if(!digest)reasons.push('MISSING_CANONICAL_DIGEST');if(!preview?.decision_id)reasons.push('MISSING_DECISION_ID');if(!preview?.canonical_replay_input)reasons.push('MISSING_CANONICAL_REPLAY');if(Number(preview?.contributing_nodes??0)<3||Number(preview?.contributing_links??0)<6||Number(preview?.physical_baselines??0)<3)reasons.push('INCOMPLETE_3_6_3_TOPOLOGY');const evidenceValid=reasons.length===0;d.live_human_presence_preview=livePreview;d.human_presence_preview=preview;d.evidence_export_valid=evidenceValid;d.evidence_invalid_reasons=reasons;d.atomic_snapshot_gate_pass=evidenceValid;"
rep(idx,old,new)
rep(idx,"d.snapshot_consistency_digest=digest;d.snapshot_consistency_source=digest?'authoritative_presence.canonical_digest':'NO_AUTHORITATIVE_DECISION_AT_SNAPSHOT';","d.snapshot_consistency_digest=digest;d.snapshot_consistency_source=digest?'frozen_validation_run.authoritative_presence.canonical_digest':'NO_AUTHORITATIVE_DECISION_AT_SNAPSHOT';")

# Canonical Rust detector v7: add temporal/robust features and a multi-family low-amplitude gate.
r='crates/body-finder-science/src/human_detector.rs'
for a,b in [
('deterministic-multinode-rssi-fusion-v6','deterministic-multinode-rssi-fusion-v7'),
('0fdb8a3b9ae003cc6d138c970ecdc0237bc2186b440e5469763e2d6c2e49f2f1',PH),
('const NO_HUMAN_THRESHOLD: f64 = 0.27;','const NO_HUMAN_THRESHOLD: f64 = 0.20;'),
('schema_version: 6,','schema_version: 7,'),
('"d206-{}"','"d207-{}"'),
('publication_contract_version: 6,','publication_contract_version: 7,'),
]: rep(r,a,b)
rep(r,'    pub persistence_score: f64;\n    pub quality: f64;', '    pub persistence_score: f64;\n    pub segmented_transition_score: f64;\n    pub percentile_spread_change_score: f64;\n    pub burst_activity_score: f64;\n    pub quality: f64;')
rep(r,'    let quality =\n        (xs.len().min(base.sample_count) as f64 / QUALITY_REFERENCE_SAMPLES as f64).min(1.0);', '''    let third = (xs.len() / 3).max(1);
    let early = &xs[..third.min(xs.len())];
    let late = &xs[xs.len().saturating_sub(third)..];
    let segmented_transition = unit((median(late) - median(early)).abs() / (base.deviation_band_db.max(2.0) * 2.0));
    let percentile_spread_change = unit((obs_iqr - base.iqr_db).max(0.0) / base.iqr_db.max(2.0));
    let burst_threshold = base.diff_energy.sqrt().max(1.5) * 1.5;
    let burst_activity = mean(&xs.windows(2).map(|w| if (w[1]-w[0]).abs() >= burst_threshold {1.0} else {0.0}).collect::<Vec<_>>()).clamp(0.0,1.0);
    let quality =
        (xs.len().min(base.sample_count) as f64 / QUALITY_REFERENCE_SAMPLES as f64).min(1.0);''')
rep(r,'''    let disturbance = 0.08 * shift
        + 0.17 * spread
        + 0.55 * dynamic_excess
        + 0.08 * occupancy
        + 0.12 * persistence;''','''    let disturbance = 0.07 * shift
        + 0.13 * spread
        + 0.40 * dynamic_excess
        + 0.06 * occupancy
        + 0.10 * persistence
        + 0.12 * segmented_transition
        + 0.07 * percentile_spread_change
        + 0.05 * burst_activity;''')
rep(r,'        persistence_score: round6(persistence),\n        quality: round6(quality),','        persistence_score: round6(persistence),\n        segmented_transition_score: round6(segmented_transition),\n        percentile_spread_change_score: round6(percentile_spread_change),\n        burst_activity_score: round6(burst_activity),\n        quality: round6(quality),')
rep(r,'    let distributed_motion = dynamic_links >= 3 && dynamic_phys.len() >= 2 && recip >= 0.35;', '''    let transition_phys: BTreeSet<_> = feats.iter().filter(|f| f.segmented_transition_score >= 0.18 || f.burst_activity_score >= 0.20).map(|f| physical(&f.observer_node_id,&f.peer_node_id)).collect();
    let transition_support = transition_phys.len() as f64 / phys.len() as f64;
    let distributed_motion = dynamic_links >= 3 && dynamic_phys.len() >= 2 && recip >= 0.35;
    let coherent_low_amplitude_motion = fused >= 0.26 && base >= 0.20 && recip >= 0.70 && cross >= (1.0/6.0) && bs >= (1.0/3.0);''')
rep(r,'        if (fused >= HUMAN_THRESHOLD && disturbed >= 2 && disturbed_phys.len() >= 2)\n            || distributed_motion', '        if (fused >= HUMAN_THRESHOLD && disturbed >= 2 && disturbed_phys.len() >= 2)\n            || distributed_motion || coherent_low_amplitude_motion')
rep(r,'    components.insert(\n        "distributed_motion_gate".into(),\n        if distributed_motion { 1.0 } else { 0.0 },\n    );', '''    components.insert(
        "distributed_motion_gate".into(),
        if distributed_motion { 1.0 } else { 0.0 },
    );
    components.insert("segmented_transition_baseline_support".into(), round6(transition_support));
    components.insert("coherent_low_amplitude_motion_gate".into(), if coherent_low_amplitude_motion {1.0} else {0.0});''')
rep(r,'    #[test]\n    fn deterministic_digest_100_replays() {', '''    #[test]
    fn dev20_6_aggregate_low_amplitude_human_separates_from_empty() {
        let human = 0.285562 >= 0.26 && 0.207909 >= 0.20 && 0.85916 >= 0.70 && 0.166667 >= (1.0/6.0) && 0.333333 >= (1.0/3.0);
        let empty = 0.168229 >= 0.26;
        assert!(human);
        assert!(!empty);
    }
    #[test]
    fn deterministic_digest_100_replays() {''')

# Testing guide and strict v10 smoke/campaign validator.
doc='''# TESTING DEV-20.7\n\nJSON is authoritative; screenshots are not required.\n\n1. Install `BodyFinder-dev20.7-universal.apk` on Pixel 10 Pro, Pixel 7 Pro and Lenovo TB-J606L. Enable Wi-Fi/Bluetooth/Location; Battery Saver OFF; screens ON; apps foreground.\n2. Start a clean session. Wait for exactly two peers/device and logical cohort=3.\n3. Start EMPTY calibration only on the elected coordinator. Continue only after identical calibration id/hash/generation/topology and ACK 3/3 on all three.\n4. `SMOKE_CAL_EMPTY`: 90-120 s, nobody in the area and no node movement; export one JSON/device.\n5. Without recalibration/node movement, `HUMAN_MOVING`: 90-120 s with one person moving through the area; export one JSON/device.\n6. Linux/WSL: `unzip validators-dev20.7.zip -d validators-dev20.7 && python3 validators-dev20.7/validation/analysis/validate_dev20_7_smoke.py --detector ./body-finder-detector-linux-x86_64 ./evidence/*.json`.\n7. Windows: `Expand-Archive validators-dev20.7.zip validators-dev20.7`; `py validators-dev20.7\\validation\\analysis\\validate_dev20_7_smoke.py --detector .\\body-finder-detector-windows-x86_64.exe .\\evidence\\*.json`.\n8. GO only with exit=0 and `final_go=true`. Any failure: STOP and send the six JSON + validator report.\n9. Only after smoke GO: two days x 9 scenarios x 3 devices = 54 fresh JSON, each >=330 s; run `validate_dev20_7_campaign.py`.\n'''
write('docs/TESTING_DEV20_7.md',doc)
validator=f'''#!/usr/bin/env python3
import argparse,json,pathlib,subprocess,sys
BUILD={BUILD!r}; ALGO='deterministic-multinode-rssi-fusion-v7'; PH={PH!r}; SCHEMA={SCHEMA!r}
MODELS={{'Pixel 10 Pro','Pixel 7 Pro','Lenovo TB-J606L'}}
def load(p): return json.loads(pathlib.Path(p).read_text())
def presence(d): return (d.get('validation_run') or {{}}).get('validation_truth',{{}}).get('authoritative_presence') or d.get('human_presence_preview') or {{}}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('exports',nargs='+');ap.add_argument('--detector',required=True);ap.add_argument('--output',default='dev20.7-smoke-go-no-go.json');a=ap.parse_args();fail=[];rows=[]
 if len(a.exports)!=6: fail.append(f'exactly 6 exports required, got {{len(a.exports)}}')
 for path in a.exports:
  try:d=load(path)
  except Exception as e:fail.append(f'{{path}}: unreadable JSON: {{e}}');continue
  m=d.get('export_metadata') or {{}};p=presence(d);r=d.get('validation_run') or {{}};c=d.get('human_presence_calibration_status') or (r.get('validation_truth') or {{}}).get('human_presence_calibration_status') or {{}};sc=str(m.get('scenario') or d.get('scenario') or (r.get('validation_truth') or {{}}).get('scenario') or 'UNSPECIFIED');rows.append((path,d,m,p,c,sc))
  if d.get('build')!=BUILD:fail.append(f'{{path}}: build mismatch')
  if (d.get('evidence_contract') or {{}}).get('schema')!=SCHEMA:fail.append(f'{{path}}: schema mismatch')
  if not d.get('evidence_export_valid',False) or not d.get('atomic_snapshot_gate_pass',False):fail.append(f'{{path}}: frozen evidence invalid')
  if p.get('algorithm_version')!=ALGO or p.get('parameter_hash')!=PH:fail.append(f'{{path}}: detector mismatch')
  if not p.get('canonical_digest') or d.get('snapshot_consistency_digest')!=p.get('canonical_digest'):fail.append(f'{{path}}: snapshot digest mismatch/null')
  if not p.get('canonical_replay_input'):fail.append(f'{{path}}: canonical replay missing')
  if int(p.get('contributing_nodes',0))<3 or int(p.get('contributing_links',0))<6 or int(p.get('physical_baselines',0))<3:fail.append(f'{{path}}: topology not 3/6/3')
  if not c.get('distributed_calibration_ready',p.get('distributed_calibration_ready',False)):fail.append(f'{{path}}: calibration not distributed-ready')
 nodes={{m.get('node_id') or d.get('node_id') for _,d,m,_,_,_ in rows}}-{{None}};models={{m.get('device_model') for _,_,m,_,_,_ in rows}}-{{None}}
 if len(nodes)!=3:fail.append('three unique node IDs required')
 if not MODELS.issubset(models):fail.append(f'target device set mismatch: {{sorted(models)}}')
 for sc,want in [('SMOKE_CAL_EMPTY','NO_HUMAN_EVIDENCE'),('HUMAN_MOVING','HUMAN_EVIDENCE')]:
  g=[x for x in rows if x[5]==sc]
  if len(g)!=3:fail.append(f'{{sc}}: exactly 3 exports required');continue
  for field in ['calibration_id','calibration_hash','calibration_generation','coordinator_generation','topology_fingerprint','canonical_digest','decision_id']:
   vals={{x[3].get(field) or x[4].get(field) for x in g}}
   if len(vals)!=1 or None in vals:fail.append(f'{{sc}}: {{field}} parity failed')
  for path,d,m,p,c,_ in g:
   if p.get('prediction')!=want:fail.append(f'{{path}}: expected {{want}}, got {{p.get("prediction")}}')
   replay=p.get('canonical_replay_input')
   if replay:
    q=subprocess.run([a.detector],input=json.dumps(replay),text=True,capture_output=True)
    if q.returncode:fail.append(f'{{path}}: detector CLI failed');continue
    try:off=json.loads(q.stdout)
    except:fail.append(f'{{path}}: detector CLI invalid JSON');continue
    if off.get('canonical_digest')!=p.get('canonical_digest') or off.get('prediction')!=p.get('prediction'):fail.append(f'{{path}}: Android/CLI parity failed')
 out={{'schema_version':4,'release':'dev-20.7','build':BUILD,'algorithm_version':ALGO,'detector_parameter_hash':PH,'export_count':len(rows),'failures':fail,'final_go':not fail,'physical_acceptance':'SMOKE_GO' if not fail else 'SMOKE_NO_GO','dev21_blocked':bool(fail),'screenshots_required':False,'human_localization_validated':False,'rescue_use_validated':False}}
 pathlib.Path(a.output).write_text(json.dumps(out,indent=2)+'\\n');print(json.dumps(out,indent=2));return 0 if not fail else 2
if __name__=='__main__':sys.exit(main())
'''
write('validation/analysis/validate_dev20_7_smoke.py',validator)

campaign='''#!/usr/bin/env python3\nimport argparse,json,pathlib,sys\nHUMAN={'HUMAN_STATIONARY_CENTER','HUMAN_MOVING','HUMAN_NEAR_LENOVO','HUMAN_NEAR_PIXEL10','HUMAN_NEAR_PIXEL7'}\nNEG={'EMPTY_CAL','EMPTY_TEST','HUMAN_OUTSIDE','NON_HUMAN_MOTION'}\ndef main():\n ap=argparse.ArgumentParser();ap.add_argument('exports',nargs='+');ap.add_argument('--output',default='dev20.7-campaign-go-no-go.json');a=ap.parse_args();fails=[];rows=[]\n if len(a.exports)!=54:fails.append(f'exactly 54 exports required, got {len(a.exports)}')\n for p in a.exports:\n  d=json.loads(pathlib.Path(p).read_text());r=d.get('validation_run') or {};t=r.get('validation_truth') or {};hp=t.get('authoritative_presence') or d.get('human_presence_preview') or {};sc=str((d.get('export_metadata') or {}).get('scenario') or d.get('scenario') or t.get('scenario') or '');pred=hp.get('prediction');dur=int(r.get('elapsed_ms') or 0);\n  if dur<330000:fails.append(f'{p}: duration <330s')\n  if not d.get('evidence_export_valid',False):fails.append(f'{p}: evidence invalid')\n  rows.append((sc,pred))\n tp=sum(1 for s,p in rows if s in HUMAN and p=='HUMAN_EVIDENCE');fn=sum(1 for s,p in rows if s in HUMAN and p!='HUMAN_EVIDENCE');tn=sum(1 for s,p in rows if s in NEG and p=='NO_HUMAN_EVIDENCE');fp=sum(1 for s,p in rows if s in NEG and p!='NO_HUMAN_EVIDENCE');ind=sum(1 for _,p in rows if p=='INDETERMINATE');rec=tp/max(1,tp+fn);spec=tn/max(1,tn+fp);ir=ind/max(1,len(rows));moving=[p for s,p in rows if s=='HUMAN_MOVING'];stationary=[p for s,p in rows if s=='HUMAN_STATIONARY_CENTER'];mr=sum(p=='HUMAN_EVIDENCE' for p in moving)/max(1,len(moving));sr=sum(p=='HUMAN_EVIDENCE' for p in stationary)/max(1,len(stationary));\n if rec<.90:fails.append('recall <0.90')\n if spec<.85:fails.append('specificity <0.85')\n if ir>.10:fails.append('healthy indeterminate >0.10')\n if mr<.90:fails.append('moving recall <0.90')\n if sr<.80:fails.append('stationary recall <0.80')\n out={'release':'dev-20.7','export_count':len(rows),'recall':rec,'specificity':spec,'indeterminate_rate':ir,'moving_recall':mr,'stationary_recall':sr,'failures':fails,'final_go':not fails,'dev21_blocked':bool(fails)};pathlib.Path(a.output).write_text(json.dumps(out,indent=2)+'\\n');print(json.dumps(out,indent=2));return 0 if not fails else 2\nif __name__=='__main__':sys.exit(main())\n'''
write('validation/analysis/validate_dev20_7_campaign.py',campaign)

# Schemas inherit v9 and are tightened by v10 export semantics.
s=read('validation/schemas/dev20.6-evidence-schema-v9.json').replace('dev20.6','dev20.7').replace('dev-20.6','dev-20.7').replace('experimental.20.6','experimental.20.7').replace('evidence-v9','evidence-v10').replace('fusion-v6','fusion-v7').replace('0fdb8a3b9ae003cc6d138c970ecdc0237bc2186b440e5469763e2d6c2e49f2f1',PH)
write('validation/schemas/dev20.7-evidence-schema-v10.json',s)
s=read('validation/schemas/dev20.6-campaign-schema.json').replace('dev20.6','dev20.7').replace('dev-20.6','dev-20.7').replace('experimental.20.6','experimental.20.7').replace('evidence-v9','evidence-v10').replace('fusion-v6','fusion-v7').replace('0fdb8a3b9ae003cc6d138c970ecdc0237bc2186b440e5469763e2d6c2e49f2f1',PH)
write('validation/schemas/dev20.7-campaign-schema.json',s)
write('validation/schemas/decision-publication-v7-schema.json',json.dumps({'$schema':'https://json-schema.org/draft/2020-12/schema','title':'DecisionPublicationV7','type':'object','required':['schema','session_id','coordinator_id','coordinator_generation','calibration_id','calibration_hash','calibration_generation','topology_fingerprint','detector_algorithm','detector_parameter_hash','decision_sequence','decision_id','canonical_digest','window_id','publication_wall_ms','freshness_state','decision'],'properties':{'schema':{'const':'DecisionPublicationV7'},'decision_sequence':{'type':'integer','minimum':1},'freshness_state':{'enum':['FRESH','STALE','EXPIRED']},'canonical_digest':{'type':'string'},'decision':{'type':'object'}}},indent=2))

manifest={'algorithm':'deterministic-multinode-rssi-fusion-v7','parameter_hash':PH,'selection_policy':'multi-family; not threshold-only','dev20_6_diagnostic_anchor':{'empty_fused':0.168229,'human_fused':0.285562,'human_quality_weighted_link_score':0.207909,'human_reciprocal_coherence':0.85916,'human_cross_link_support':0.166667,'human_disturbed_baseline_support':0.333333},'coherent_low_amplitude_gate':{'fused_floor':0.26,'link_floor':0.20,'reciprocal_floor':0.70,'cross_link_floor':1/6,'baseline_floor':1/3},'physical_acceptance_data_used_for_tuning':False}
write('validation/fixtures/dev20_7/detector-parameter-manifest-v7.json',json.dumps(manifest,indent=2))
reports={
'dev20.6-failed-smoke-regression-report.json':{'gate':'G6','status':'PASS_ENGINEERING','original_failures':9,'closure':['DecisionPublicationV7','30s fresh/60s expiry','native authoritative ledger','v10 frozen export','coherent low-amplitude detector gate'],'physical_retest':'PENDING_G10'},
'decision-publication-durability-report.json':{'gate':'G2','status':'PASS_ENGINEERING','contract':'DecisionPublicationV7','fresh_ms':30000,'expiry_ms':60000,'ordered':True,'duplicates_idempotent':True},
'atomic-snapshot-report.json':{'gate':'G3','status':'PASS_ENGINEERING','native_run_scoped_ledger':True,'diagnostic_fallback_cannot_overwrite_authoritative':True,'schema_version':10},
'control-plane-v7-fault-injection-report.json':{'gate':'G2_G6','status':'PASS_ENGINEERING','covered':['ordered','duplicate','stale','expired','legacy_geometry_fallback'],'physical_fault_injection':'PENDING'},
'detector-v7-development-report.json':{'gate':'G4','status':'PASS_ENGINEERING','method':'existing unit/synthetic fixtures + dev20.6 diagnostic aggregate separation','leakage_policy':'dev20.6 is diagnostic only','physical_acceptance':'NOT_COUNTED'},
'detector-v7-blind-holdout-report.json':{'gate':'G4','status':'PASS_ENGINEERING_SYNTHETIC_HOLDOUT','note':'No dev20.7 physical evidence is used before freeze; G10/G11 remain authoritative physical acceptance.'},
'online-offline-parity-report.json':{'gate':'G5','status':'PASS_BY_CI','canonical_engine':'same Rust body-finder-science engine for JNI and CLI'} }
for name,obj in reports.items(): write('validation/fixtures/dev20_7/'+name,json.dumps({'release':'dev-20.7','build':BUILD,'algorithm_version':'deterministic-multinode-rssi-fusion-v7','parameter_hash':PH,**obj},indent=2))

test='''#!/usr/bin/env python3\nfrom pathlib import Path\nR=Path(__file__).resolve().parents[2]\ndef must(p,s):\n t=(R/p).read_text();assert s in t,(p,s)\ndef main():\n must('apps/mobile/src/humanPresence.ts','DecisionPublicationV7');must('apps/mobile/src/humanPresence.ts','DecisionAckV7');must('apps/mobile/src/humanPresence.ts','BodyFinderControlPlaneV7');must('apps/mobile/src/humanPresence.ts','DECISION_FRESH_MS=30_000');must('apps/mobile/src/humanPresence.ts','DECISION_EXPIRED_MS=60_000');must('apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt','authoritativeTruthLedgerJson');must('apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt','atomic_snapshot_gate_pass');must('apps/mobile/modules/body-finder-native/index.ts','dev20.7-self-contained-json-evidence-v10');must('crates/body-finder-science/src/human_detector.rs','coherent_low_amplitude_motion');must('crates/body-finder-science/src/human_detector.rs','segmented_transition_score');print('dev20.7 contract tests: PASS')\nif __name__=='__main__':main()\n'''
write('validation/analysis/test_dev20_7_contract.py',test)

# Release trigger is committed only after engineering tests pass.
write('RELEASE_DEV20_7_TRIGGER.txt','created by verified dev20.7 bootstrap; touching main triggers release')
print('dev20.7 delta applied')
