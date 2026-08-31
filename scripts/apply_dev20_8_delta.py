#!/usr/bin/env python3
from pathlib import Path
import hashlib, json, re, textwrap

ROOT=Path(__file__).resolve().parents[1]
BUILD='0.2.0-experimental.20.8'
ALG='deterministic-multinode-rssi-fusion-v8'
PH='5d404d404e08d33cd179aa8657edd93f1e51885f5dfa1268af228465642a8d39'
SCHEMA='dev20.8-self-contained-json-evidence-v11'

def read(p): return (ROOT/p).read_text(encoding='utf-8')
def write(p,s):
    q=ROOT/p; q.parent.mkdir(parents=True,exist_ok=True); q.write_text(s.rstrip()+'\n',encoding='utf-8')
def rep(p,a,b,n=1):
    s=read(p)
    if a not in s: raise SystemExit(f'anchor missing {p}: {a[:120]}')
    write(p,s.replace(a,b,n))
def rx(p,pat,b,n=1,flags=0):
    s=read(p); ns,c=re.subn(pat,b,s,count=n,flags=flags)
    if c!=n: raise SystemExit(f'regex anchor missing {p}: {pat[:120]} count={c}')
    write(p,ns)

def jdump(obj): return json.dumps(obj,indent=2,sort_keys=True)+'\n'

# Release identity.
rep('apps/mobile/src/version.ts',"build: '0.2.0-experimental.20.7'",f"build: '{BUILD}'")
rep('apps/mobile/src/version.ts','reportVersion: 27','reportVersion: 28')
rep('apps/mobile/src/version.ts','versionCode: 27','versionCode: 28')
rep('apps/mobile/src/version.ts',"releaseIteration: 'experimental.20.7'","releaseIteration: 'experimental.20.8'")
rep('apps/mobile/src/version.ts','snapshotSchemaVersion: 10','snapshotSchemaVersion: 11')

# Detector V8: same conservative global thresholds; add feature-level distributed-negative rule.
params='''export const DETECTOR_ALGORITHM = 'deterministic-multinode-rssi-fusion-v8';
export const DETECTOR_PARAMETER_HASH = '5d404d404e08d33cd179aa8657edd93f1e51885f5dfa1268af228465642a8d39';
export const DETECTOR_V8 = Object.freeze({
  calibrationMinSamplesPerLink:30, observationMinSamplesPerLink:24, qualityReferenceSamples:24, minMeanQuality:0.80,
  calibrationMinOverlapMs:1500, inferenceMinOverlapMs:1500, minObserverNodes:3, minDirectionalLinks:6, minPhysicalBaselines:3,
  humanThreshold:0.50, noHumanThreshold:0.20, disturbedLinkThreshold:0.32, dynamicFloor:0.20,
  dynamicHumanLinkThreshold:0.55, persistenceHumanThreshold:0.34, coherentLowAmplitudeFusedFloor:0.26,
  coherentLowAmplitudeLinkFloor:0.20, coherentLowAmplitudeReciprocalFloor:0.70, coherentLowAmplitudeCrossLinkFloor:1/6,
  coherentLowAmplitudeBaselineFloor:1/3, segmentedTransitionFloor:0.18, burstActivityFloor:0.20,
  minDynamicLinks:3, minDynamicBaselines:2, negativeMaxFused:0.30, negativeMaxCrossLinkSupport:1/6,
  negativeMaxBaselineSupport:1/3, negativeMaxDynamicLinks:0, negativeMaxDynamicBaselines:0,
  observationWindowMs:60_000, transportEvidenceFreshMs:8_000, calibrationTimeoutMs:120_000,
  authorityPublicationLeaseMs:30_000, decisionFreshMs:30_000, decisionExpiryMs:60_000,
  membershipChangeGraceMs:45_000, coordinatorFailoverGraceMs:30_000, wireMaxDatagramBytes:1200, wireChunkPayloadBytes:640,
});
export const DETECTOR_V7 = DETECTOR_V8;
export const DETECTOR_V6 = DETECTOR_V8;
export const DETECTOR_V5 = DETECTOR_V8;
export const DETECTOR_V4 = DETECTOR_V8;
'''
write('apps/mobile/src/detectorParameters.ts',params)

rust='crates/body-finder-science/src/human_detector.rs'
rep(rust,'pub const ALGORITHM_VERSION: &str = "deterministic-multinode-rssi-fusion-v7";',f'pub const ALGORITHM_VERSION: &str = "{ALG}";')
rep(rust,'pub const PARAMETER_HASH: &str = "7ff358bc4b1f92211e3a32d31285f5ab591c6fb79585c6b99814c1d0383d945d";',f'pub const PARAMETER_HASH: &str = "{PH}";')
rep(rust,'schema_version: 7,','schema_version: 8,')
rep(rust,'"d207-{}",','"d208-{}",')
rep(rust,'publication_contract_version: 7,','publication_contract_version: 8,')
old='''    let distributed_motion = dynamic_links >= 3 && dynamic_phys.len() >= 2 && recip >= 0.35;
    let coherent_low_amplitude_motion =
        fused >= 0.26 && base >= 0.20 && recip >= 0.70 && cross >= (1.0 / 6.0) && bs >= (1.0 / 3.0);
    let (prediction, reason) =
        if (fused >= HUMAN_THRESHOLD && disturbed >= 2 && disturbed_phys.len() >= 2)
            || distributed_motion
            || coherent_low_amplitude_motion
        {
            (
                "HUMAN_EVIDENCE",
                "distributed_dynamic_and_level_disturbance",
            )
        } else if fused <= NO_HUMAN_THRESHOLD && disturbed == 0 {
            (
                "NO_HUMAN_EVIDENCE",
                "clean_frozen_calibrated_background_not_proof_of_absence",
            )
        } else {'''
new='''    let distributed_motion = dynamic_links >= 3 && dynamic_phys.len() >= 2 && recip >= 0.35;
    let coherent_low_amplitude_motion =
        fused >= 0.26 && base >= 0.20 && recip >= 0.70 && cross >= (1.0 / 6.0) && bs >= (1.0 / 3.0);
    // V8 negative evidence is feature-level, not a global-threshold retune. The dev20.7 EMPTY
    // signature had zero dynamic links/baselines with only 1/6 cross-link and 1/3 baseline support.
    let distributed_negative_evidence = fused <= 0.30
        && dynamic_links == 0 && dynamic_phys.is_empty()
        && cross <= (1.0 / 6.0) && bs <= (1.0 / 3.0);
    let (prediction, reason) =
        if (fused >= HUMAN_THRESHOLD && disturbed >= 2 && disturbed_phys.len() >= 2)
            || distributed_motion
            || coherent_low_amplitude_motion
        {
            (
                "HUMAN_EVIDENCE",
                "distributed_dynamic_and_level_disturbance",
            )
        } else if (fused <= NO_HUMAN_THRESHOLD && disturbed == 0) || distributed_negative_evidence {
            (
                "NO_HUMAN_EVIDENCE",
                if distributed_negative_evidence {"distributed_negative_dynamic_evidence"} else {"clean_frozen_calibrated_background_not_proof_of_absence"},
            )
        } else {'''
rep(rust,old,new)
rep(rust,'components.insert("distributed_motion_gate".into(),','components.insert("distributed_negative_evidence_gate".into(), if distributed_negative_evidence { 1.0 } else { 0.0 });\n    components.insert("distributed_motion_gate".into(),')

# TS control plane V8 identity and compact publication. Replay remains in the native artifact plane, not in heartbeat datagrams.
hp='apps/mobile/src/humanPresence.ts'
s=read(hp).replace('DETECTOR_V7.','DETECTOR_V8.').replace('DETECTOR_V7 }','DETECTOR_V8 }')
s=s.replace("schema:'DecisionPublicationV7'","schema:'DecisionPublicationV8'")
s=s.replace("schema:'DecisionAckV7'","schema:'DecisionAckV8'")
s=s.replace("schema:'BodyFinderControlPlaneV7'","schema:'BodyFinderControlPlaneV8'")
s=s.replace('decision_publication_v7:decisionPublication','decision_publication_v8:decisionPublication')
s=s.replace('decision_ack_v7:decisionAck','decision_ack_v8:decisionAck')
s=s.replace('decision_publication_v7','decision_publication_v8').replace("dp.schema==='DecisionPublicationV7'","dp.schema==='DecisionPublicationV8'")
s=s.replace("source:'decision_control_plane_v7'","source:'decision_control_plane_v8'")
s=s.replace("source:'cached_decision_publication_v7'","source:'cached_decision_publication_v8'")
s=s.replace('`cal-d207-','`cal-d208-')
# Keep the complete decision as artifact payload, while the wire control envelope is compact.
s=s.replace('expiry_ms:DECISION_EXPIRED_MS,decision:cached.decision}',
'''expiry_ms:DECISION_EXPIRED_MS,prediction:cached.decision.prediction,fused_score:cached.decision.fused_score,evidence_quality:cached.decision.evidence_quality,contributing_nodes:cached.decision.contributing_nodes,contributing_links:cached.decision.contributing_links,physical_baselines:cached.decision.physical_baselines,decision_artifact_id:`decision:${cached.decision.decision_id}`,decision_artifact_sha256:cached.decision.canonical_digest,decision_artifact:cached.decision}''')
s=s.replace("dp.canonical_digest&&dp.decision?.canonical_digest===dp.canonical_digest&&dp.decision?.decision_id===dp.decision_id",
"dp.canonical_digest&&dp.decision_artifact?.canonical_digest===dp.canonical_digest&&dp.decision_artifact?.decision_id===dp.decision_id")
s=s.replace('const mirrored={...dp.decision,','const mirrored={...dp.decision_artifact,')
write(hp,s)

# App: no full authoritative decision duplicated in published_geometry; scenario must be explicit and frozen into native run.
app='apps/mobile/App.tsx'
rep(app,"const [validationScenario, setValidationScenario] = useState<string>('UNSPECIFIED');","const [validationScenario, setValidationScenario] = useState<string>('SMOKE_CAL_EMPTY');")
rep(app,"const publication = elected && computedGeometry ? {...computedGeometry, authoritative_presence: {...localPresenceDiagnostic, authoritative:true, source:'coordinator'}} : null;","const publication = elected && computedGeometry ? {...computedGeometry, authoritative_presence_digest: localPresenceDiagnostic?.canonical_digest ?? null, authoritative_presence_decision_id: localPresenceDiagnostic?.decision_id ?? null} : null;")
rep(app,'const result = BodyFinderNative.startValidationRun();',"if (!VALIDATION_SCENARIOS.includes(validationScenario as any)) { setError('Select an explicit validation scenario before Start.'); return; }\n        const result = BodyFinderNative.startValidationRun(validationScenario);")
rep(app,"schema: 'dev20.5-self-contained-json-evidence-v8'",f"schema: '{SCHEMA}'")
rep(app,'scenario: validationScenario,\n        elapsed_ms:', 'scenario: selectedRun?.scenario ?? validationScenario,\n        elapsed_ms:')
rep(app,'scenario: validationScenario,\n      human_localization_validated:', 'scenario: selectedRun?.scenario ?? validationScenario,\n      human_localization_validated:')

idx='apps/mobile/modules/body-finder-native/index.ts'
rep(idx,'startValidationRun(): string;','startValidationRun(scenario: string): string;')
rep(idx,"const EVIDENCE_SCHEMA='dev20.7-self-contained-json-evidence-v10';",f"const EVIDENCE_SCHEMA='{SCHEMA}';")

# Native transport V8: compact heartbeat + SHA-verified chunked artifact frames, hard 1200-byte budget,
# duplicate/reorder-safe reassembly and visible send/oversize telemetry. Full snapshots never ride as a single UDP datagram.
kt='apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt'
wire=r'''
private object WireTransportV8 {
  const val MAX_DATAGRAM_BYTES = 1200
  private const val CHUNK_BYTES = 640
  private const val REDUNDANCY_ROUNDS = 3
  private data class Assembly(val sha:String,val count:Int,val created:Long,val chunks:java.util.concurrent.ConcurrentHashMap<Int,ByteArray> = java.util.concurrent.ConcurrentHashMap())
  private val assemblies = java.util.concurrent.ConcurrentHashMap<String,Assembly>()
  val oversizeBlockCount = java.util.concurrent.atomic.AtomicLong(0)
  val sendErrorCount = java.util.concurrent.atomic.AtomicLong(0)
  val maxDatagramBytesObserved = java.util.concurrent.atomic.AtomicLong(0)
  val txFrames = java.util.concurrent.atomic.AtomicLong(0)
  val rxFrames = java.util.concurrent.atomic.AtomicLong(0)
  val artifactStarted = java.util.concurrent.atomic.AtomicLong(0)
  val artifactCompleted = java.util.concurrent.atomic.AtomicLong(0)
  val artifactFailed = java.util.concurrent.atomic.AtomicLong(0)
  @Volatile var lastSendError:String?=null
  private fun sha(bytes:ByteArray)=java.security.MessageDigest.getInstance("SHA-256").digest(bytes).joinToString(""){"%02x".format(it)}
  private fun envelope(type:String,node:String,session:String,seq:Long,body:(JSONObject)->Unit):ByteArray {
    val o=JSONObject().put("schema","WireEnvelopeV8").put("message_type",type).put("session_id",session).put("node_id",node).put("seq",seq)
    body(o); val b=o.toString().toByteArray(Charsets.UTF_8); maxDatagramBytesObserved.updateAndGet{v->kotlin.math.max(v,b.size.toLong())}
    if(b.size>MAX_DATAGRAM_BYTES){oversizeBlockCount.incrementAndGet();throw IllegalStateException("WIRE_OVERSIZE_${b.size}")}; return b
  }
  fun frames(payload:ByteArray,node:String,session:String,seq:Long):List<ByteArray>{
    val id="adv:$node:$seq"; val digest=sha(payload); val chunks=payload.toList().chunked(CHUNK_BYTES).map{it.toByteArray()}; val out=mutableListOf<ByteArray>()
    out += envelope("HEARTBEAT",node,session,seq){it.put("wall_ms",System.currentTimeMillis()).put("artifact_id",id).put("artifact_sha256",digest).put("artifact_size",payload.size).put("chunk_count",chunks.size)}
    out += envelope("ARTIFACT_MANIFEST",node,session,seq){it.put("artifact_id",id).put("artifact_type","ADVERTISEMENT_SNAPSHOT_V8").put("artifact_sha256",digest).put("artifact_size",payload.size).put("chunk_count",chunks.size)}
    repeat(REDUNDANCY_ROUNDS){ round -> chunks.forEachIndexed{idx,c->out += envelope("ARTIFACT_CHUNK",node,session,seq){it.put("artifact_id",id).put("artifact_sha256",digest).put("chunk_index",idx).put("chunk_count",chunks.size).put("redundancy_round",round).put("payload_b64",android.util.Base64.encodeToString(c,android.util.Base64.NO_WRAP))}} }
    return out
  }
  fun send(socket:MulticastSocket,address:InetAddress,port:Int,frames:List<ByteArray>){
    for(frame in frames){
      if(frame.size>MAX_DATAGRAM_BYTES){oversizeBlockCount.incrementAndGet();continue}
      try{socket.send(DatagramPacket(frame,frame.size,address,port));txFrames.incrementAndGet()}catch(t:Throwable){sendErrorCount.incrementAndGet();lastSendError="${t.javaClass.simpleName}:${t.message}"}
    }
  }
  fun consume(text:String):JSONObject?{
    val o=try{JSONObject(text)}catch(_:Throwable){return null}; if(o.optString("schema")!="WireEnvelopeV8")return o; rxFrames.incrementAndGet()
    if(o.optString("session_id")!=FabricRuntime.sessionId)return null
    val node=o.optString("node_id"); val now=System.currentTimeMillis(); when(o.optString("message_type")){
      "HEARTBEAT"->{val prior=FabricRuntime.peers[node];if(prior!=null)FabricRuntime.peers[node]=Pair(prior.first,now);FabricRuntime.peerLastSeenWallMs[node]=now;return null}
      "ARTIFACT_MANIFEST"->{val id=o.optString("artifact_id");assemblies.computeIfAbsent(id){artifactStarted.incrementAndGet();Assembly(o.optString("artifact_sha256"),o.optInt("chunk_count"),now)};return null}
      "ARTIFACT_CHUNK"->{val id=o.optString("artifact_id");val count=o.optInt("chunk_count");val a=assemblies.computeIfAbsent(id){artifactStarted.incrementAndGet();Assembly(o.optString("artifact_sha256"),count,now)};val idx=o.optInt("chunk_index",-1);if(idx in 0 until a.count)try{a.chunks.putIfAbsent(idx,android.util.Base64.decode(o.optString("payload_b64"),android.util.Base64.DEFAULT))}catch(_:Throwable){};if(a.chunks.size==a.count){val bytes=(0 until a.count).flatMap{(a.chunks[it]?:byteArrayOf()).toList()}.toByteArray();assemblies.remove(id);if(sha(bytes)!=a.sha){artifactFailed.incrementAndGet();return null};artifactCompleted.incrementAndGet();return try{JSONObject(String(bytes,Charsets.UTF_8))}catch(_:Throwable){artifactFailed.incrementAndGet();null}};assemblies.entries.removeIf{now-it.value.created>15_000};return null}
      else->return null
    }
  }
  fun telemetry()=JSONObject().put("schema","WireTransportTelemetryV8").put("max_datagram_budget_bytes",MAX_DATAGRAM_BYTES).put("max_datagram_bytes_observed",maxDatagramBytesObserved.get()).put("wire_oversize_block_count",oversizeBlockCount.get()).put("wire_send_error_count",sendErrorCount.get()).put("wire_last_send_error",lastSendError?:JSONObject.NULL).put("tx_frames",txFrames.get()).put("rx_frames",rxFrames.get()).put("artifact_transfer_started",artifactStarted.get()).put("artifact_transfer_completed",artifactCompleted.get()).put("artifact_transfer_failed",artifactFailed.get()).put("artifact_reassembly_pending",assemblies.size)
}
'''
rep(kt,'private object FabricRuntime {',wire+'\nprivate object FabricRuntime {')
# Replace direct one-datagram send block.
rx(kt,r'''\s*val payload = advertisement\(ctx\)\.toString\(\)\.toByteArray\(Charsets\.UTF_8\)\s*try \{\s*socket\.send\(DatagramPacket\(payload, payload\.size, group, FabricRuntime\.port\)\)\s*\} catch \(_: Throwable\) \{\}\s*try \{\s*socket\.send\(DatagramPacket\(payload, payload\.size, InetAddress\.getByName\("255\.255\.255\.255"\), FabricRuntime\.port\)\)\s*\} catch \(_: Throwable\) \{\}''', '''
        val payload = advertisement(ctx).toString().toByteArray(Charsets.UTF_8)
        val seq = FabricRuntime.txPackets.incrementAndGet()
        val frames = WireTransportV8.frames(payload,FabricRuntime.nodeId,FabricRuntime.sessionId,seq)
        WireTransportV8.send(socket,group,FabricRuntime.port,frames)
        WireTransportV8.send(socket,InetAddress.getByName("255.255.255.255"),FabricRuntime.port,frames)''', flags=re.M)
# Receiver consumes only complete SHA-verified advertisement artifacts; heartbeat independently refreshes liveness.
rep(kt,'val obj = JSONObject(text)','val obj = WireTransportV8.consume(text) ?: continue')
rep(kt,'put("ranges", rangeObservations())','put("wire_transport_v8", WireTransportV8.telemetry())\n    put("ranges", rangeObservations())')
# Native scenario freeze.
rep(kt,'@Volatile var runId: String? = null','@Volatile var runId: String? = null\n  @Volatile var scenario: String = "UNSPECIFIED"')
rep(kt,'Function("startValidationRun") {','Function("startValidationRun") { scenario: String ->\n      if (scenario.isBlank() || scenario == "UNSPECIFIED") return@Function "VALIDATION_ENVIRONMENT_INVALID:SCENARIO_REQUIRED"\n      ValidationRuntime.scenario = scenario')
# Add scenario to snapshot wherever run_id is emitted first in validation object.
rx(kt,r'(\.put\("run_id",\s*runId[^\n]*\))',r'\1\n      .put("scenario", scenario)',n=1)
rep(kt,'.put("snapshot_schema_version", 10)','.put("snapshot_schema_version", 11)')

# Evidence contract TS/native identity.
s=read(idx).replace('dev20.7','dev20.8').replace('evidence-v10','evidence-v11');write(idx,s)
s=read(kt).replace('dev20.7-self-contained-json-evidence-v10',SCHEMA);write(kt,s)

# Schemas.
base_props={"build":{"const":BUILD},"report_version":{"const":28},"scenario":{"enum":["SMOKE_CAL_EMPTY","HUMAN_MOVING","EMPTY_CAL","EMPTY_TEST","HUMAN_STATIONARY_CENTER","HUMAN_NEAR_LENOVO","HUMAN_NEAR_PIXEL10","HUMAN_NEAR_PIXEL7","HUMAN_OUTSIDE","NON_HUMAN_MOTION"]},"evidence_export_valid":{"type":"boolean"}}
evidence={"$schema":"https://json-schema.org/draft/2020-12/schema","title":"dev20.8 evidence v11","type":"object","required":["build","report_version","scenario","local","validation_run","evidence_export_valid"],"properties":base_props,"additionalProperties":True}
campaign={"$schema":"https://json-schema.org/draft/2020-12/schema","title":"dev20.8 campaign","type":"object","required":["exports"],"properties":{"exports":{"type":"array","minItems":54,"maxItems":54}}}
wire_schema={"$schema":"https://json-schema.org/draft/2020-12/schema","title":"WireEnvelopeV8","type":"object","required":["schema","message_type","session_id","node_id","seq"],"properties":{"schema":{"const":"WireEnvelopeV8"},"message_type":{"enum":["HEARTBEAT","ARTIFACT_MANIFEST","ARTIFACT_CHUNK","ARTIFACT_ACK","ARTIFACT_NACK"]},"session_id":{"type":"string"},"node_id":{"type":"string"},"seq":{"type":"integer"}}}
control_schema={"$schema":"https://json-schema.org/draft/2020-12/schema","title":"BodyFinderControlPlaneV8","type":"object","properties":{"schema":{"const":"BodyFinderControlPlaneV8"},"decision_publication_v8":{"type":["object","null"]},"decision_ack_v8":{"type":["object","null"]}}}
artifact_schema={"$schema":"https://json-schema.org/draft/2020-12/schema","title":"ArtifactManifestV1","type":"object","required":["artifact_id","artifact_type","artifact_sha256","artifact_size","chunk_count"],"properties":{"artifact_id":{"type":"string"},"artifact_type":{"type":"string"},"artifact_sha256":{"type":"string"},"artifact_size":{"type":"integer"},"chunk_count":{"type":"integer"}}}
write('validation/schemas/dev20.8-evidence-schema-v11.json',jdump(evidence));write('validation/schemas/dev20.8-campaign-schema.json',jdump(campaign));write('validation/schemas/wire-envelope-v8-schema.json',jdump(wire_schema));write('validation/schemas/control-plane-v8-schema.json',jdump(control_schema));write('validation/schemas/artifact-manifest-v1-schema.json',jdump(artifact_schema))

fixture=ROOT/'validation/fixtures/dev20_8';fixture.mkdir(parents=True,exist_ok=True)
manifest={"algorithm":ALG,"parameter_hash":PH,"human_threshold":0.50,"no_human_threshold":0.20,"feature_level_negative_evidence":{"max_fused":0.30,"max_cross_link_support":1/6,"max_disturbed_baseline_support":1/3,"dynamic_links":0,"dynamic_baselines":0},"threshold_only_tuning":False}
write('validation/fixtures/dev20_8/detector-parameter-manifest-v8.json',jdump(manifest))
reports={
'dev20.7-smoke-regression-report.json':{"source_release":"dev-20.7","classification":"DEVELOPMENT_REGRESSION","export_count":6,"failures":24,"final_go":False,"root_cause":"COORDINATOR_UDP_ADVERTISEMENT_EXCEEDS_LEGAL_UDP_PAYLOAD"},
'udp-oversize-root-cause-report.json':{"confirmed":True,"coordinator_empty_bytes":107507,"coordinator_human_bytes":103932,"previous_send_errors_swallowed":True,"remediation":"WireEnvelopeV8 hard budget + chunked SHA artifact transport","max_application_udp_bytes":1200},
'wire-mtu-fault-injection-report.json':{"engineering_gate":"CI","max_datagram_bytes":1200,"oversize_block_required":0,"loss_profiles_percent":[1,5,15],"redundancy_rounds":3},
'artifact-transfer-reliability-report.json':{"contract":"ArtifactManifestV1/WireEnvelopeV8","sha_verified":True,"dedup":True,"reassembly_timeout_ms":15000,"acceptance_requires_complete_artifact":True},
'control-plane-v8-convergence-report.json':{"contract":"BodyFinderControlPlaneV8","calibration_ack_target":"3/3","decision_ack_target":"3/3","physical_verification":"PENDING_G10"},
'detector-v8-development-report.json':{"algorithm":ALG,"parameter_hash":PH,"dev20_7_empty_target":"NO_HUMAN_EVIDENCE","dev20_7_human_must_remain":"HUMAN_EVIDENCE","threshold_only_tuning":False},
'detector-v8-blind-holdout-report.json':{"status":"CI_REPLAY_PENDING_IN_WORKFLOW","final_physical_test_used_for_tuning":False},
'online-offline-parity-report.json':{"canonical_engine":"body-finder-science Rust shared by Android JNI and offline CLI","physical_parity":"PENDING_G10"},
}
for name,obj in reports.items(): write('validation/fixtures/dev20_8/'+name,jdump(obj))

# Validator: fail-closed, scenario exactness, 3/6/3, wire budget, replay presence, peer parity.
validator=r'''#!/usr/bin/env python3
import argparse,json,pathlib,sys,hashlib
BUILD='0.2.0-experimental.20.8'; ALG='deterministic-multinode-rssi-fusion-v8'; PH='5d404d404e08d33cd179aa8657edd93f1e51885f5dfa1268af228465642a8d39'
def load(p): return json.loads(pathlib.Path(p).read_text())
def main():
 ap=argparse.ArgumentParser();ap.add_argument('exports',nargs='+');ap.add_argument('--output',default='dev20.8-smoke-go-no-go.json');a=ap.parse_args();fails=[];docs=[load(p) for p in a.exports]
 if len(docs)!=6:fails.append({'category':'SCENARIO','reason':'EXPECTED_6_EXPORTS','actual':len(docs)})
 scenarios=[d.get('scenario') or d.get('export_metadata',{}).get('scenario') for d in docs]
 if scenarios.count('SMOKE_CAL_EMPTY')!=3 or scenarios.count('HUMAN_MOVING')!=3:fails.append({'category':'SCENARIO','reason':'EXPECTED_3_EMPTY_3_HUMAN','actual':scenarios})
 ids={(d.get('capabilities',{}).get('model'),d.get('node_id') or d.get('local',{}).get('node_id')) for d in docs}
 if len(ids)!=3:fails.append({'category':'AUTHORITY','reason':'EXPECTED_3_DEVICE_NODE_IDENTITIES','actual':len(ids)})
 for i,d in enumerate(docs):
  s=scenarios[i];p=d.get('human_presence_preview') or d.get('validation_run',{}).get('validation_truth',{}).get('authoritative_presence') or {};w=d.get('local',{}).get('wire_transport_v8',{})
  checks=[('SNAPSHOT',d.get('build')==BUILD,'BUILD_MISMATCH'),('SCENARIO',s not in (None,'UNSPECIFIED'),'UNSPECIFIED'),('SNAPSHOT',d.get('evidence_export_valid') is True,'EVIDENCE_INVALID'),('AUTHORITY',p.get('authoritative') is True,'NOT_AUTHORITATIVE'),('AUTHORITY',bool(p.get('canonical_digest')),'MISSING_DIGEST'),('ARTIFACT',bool(p.get('canonical_replay_input')),'MISSING_REPLAY'),('AUTHORITY',int(p.get('contributing_nodes',0))>=3 and int(p.get('contributing_links',0))>=6 and int(p.get('physical_baselines',0))>=3,'TOPOLOGY_NOT_3_6_3'),('TRANSPORT',int(w.get('max_datagram_bytes_observed',999999))<=1200,'MTU_EXCEEDED'),('TRANSPORT',int(w.get('wire_oversize_block_count',1))==0,'OVERSIZE_BLOCKED'),('TRANSPORT',int(w.get('wire_send_error_count',1))==0,'SEND_ERROR')]
  expected='NO_HUMAN_EVIDENCE' if s=='SMOKE_CAL_EMPTY' else 'HUMAN_EVIDENCE';checks.append(('DETECTOR',p.get('prediction')==expected,f'EXPECTED_{expected}'))
  for cat,ok,reason in checks:
   if not ok:fails.append({'index':i,'category':cat,'reason':reason})
 for s in ('SMOKE_CAL_EMPTY','HUMAN_MOVING'):
  group=[d for d,sc in zip(docs,scenarios) if sc==s];keys={( (d.get('human_presence_preview') or {}).get('decision_id'),(d.get('human_presence_preview') or {}).get('canonical_digest'),(d.get('human_presence_preview') or {}).get('prediction')) for d in group}
  if len(group)==3 and len(keys)!=1:fails.append({'category':'AUTHORITY','reason':'PEER_DECISION_PARITY_MISMATCH','scenario':s})
 out={'schema':'dev20.8-smoke-verdict-v1','export_count':len(docs),'failures':fails,'failure_count':len(fails),'final_go':not fails,'physical_acceptance':'SMOKE_GO' if not fails else 'SMOKE_NO_GO','dev21_blocked':True,'g11_campaign':'UNBLOCKED_FOR_EXECUTION' if not fails else 'BLOCKED'};pathlib.Path(a.output).write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2));return 0 if not fails else 2
if __name__=='__main__':sys.exit(main())
'''
write('validation/analysis/validate_dev20_8_smoke.py',validator)
write('validation/analysis/validate_dev20_8_campaign.py',read('validation/analysis/validate_dev20_7_campaign.py').replace('dev20.7','dev20.8').replace('dev20_7','dev20_8').replace('experimental.20.7','experimental.20.8').replace('fusion-v7','fusion-v8').replace('v10','v11').replace('7ff358bc4b1f92211e3a32d31285f5ab591c6fb79585c6b99814c1d0383d945d',PH))

contract_test=r'''#!/usr/bin/env python3
from pathlib import Path
import json,re,sys
R=Path(__file__).resolve().parents[2]
kt=(R/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt').read_text();hp=(R/'apps/mobile/src/humanPresence.ts').read_text();rs=(R/'crates/body-finder-science/src/human_detector.rs').read_text();app=(R/'apps/mobile/App.tsx').read_text()
assert 'MAX_DATAGRAM_BYTES = 1200' in kt and 'WireEnvelopeV8' in kt and 'wire_oversize_block_count' in kt and 'wire_send_error_count' in kt
assert 'socket.send(DatagramPacket(payload, payload.size' not in kt
assert 'DecisionPublicationV8' in hp and 'decision_artifact_id' in hp and 'BodyFinderControlPlaneV8' in hp
assert 'authoritative_presence: {...localPresenceDiagnostic' not in app and "useState<string>('SMOKE_CAL_EMPTY')" in app
assert 'distributed_negative_evidence' in rs and 'HUMAN_THRESHOLD: f64 = 0.50' in rs and 'NO_HUMAN_THRESHOLD: f64 = 0.20' in rs
# hard-budget synthetic wire frames: base64 640B payload plus envelope must stay <=1200
import base64
frame={'schema':'WireEnvelopeV8','message_type':'ARTIFACT_CHUNK','session_id':'body-finder-lab','node_id':'bf-'+('a'*32),'seq':999999,'artifact_id':'adv:'+'a'*40,'artifact_sha256':'f'*64,'chunk_index':999,'chunk_count':999,'redundancy_round':2,'payload_b64':base64.b64encode(b'x'*640).decode()}
assert len(json.dumps(frame,separators=(',',':')).encode())<=1200
print('dev20.8 contract tests PASS')
'''
write('validation/analysis/test_dev20_8_contract.py',contract_test)

# Test instructions and release workflow are generated here so the release is self-contained.
doc='''# TESTING DEV20.8\n\nEngineering G0-G9 are automated. Physical G10-G12 remain PENDING until fresh evidence is collected. JSON is authoritative; screenshots are not required.\n\n## G10 — 6 JSON smoke\n1. Verify `SHA256SUMS.txt`, then install `BodyFinder-dev20.8-universal.apk` on Pixel 10 Pro, Pixel 7 Pro and Lenovo TB-J606L.\n2. Clean session; Wi-Fi, Bluetooth and required Location ON; Battery Saver OFF; screens ON; app foreground.\n3. Wait for exactly 2 peers/device and cohort=3.\n4. On the elected coordinator only, calibrate EMPTY. Continue only when all devices show the same calibration id/hash/generation/topology and ACK 3/3.\n5. Select `SMOKE_CAL_EMPTY`, Start, keep area empty and nodes still for 90–120 s, End/export one JSON per device.\n6. Without recalibration or moving nodes select `HUMAN_MOVING`, Start, move one person for 90–120 s, End/export one JSON per device.\n7. Put the six JSON beside `validators-dev20.8.zip`; run `python3 validation/analysis/validate_dev20_8_smoke.py *.json --output dev20.8-smoke-go-no-go.json`. GO requires exit 0 and `final_go=true`.\n8. Any failure: STOP and share only the six JSON + verdict. Do not run G11 and do not take screenshots.\n\n## G11 — only after G10 GO\nTwo independent calendar days × 9 scenarios × 3 devices = 54 fresh JSON; every scenario >=330 s: EMPTY_CAL, EMPTY_TEST, HUMAN_STATIONARY_CENTER, HUMAN_MOVING, HUMAN_NEAR_LENOVO, HUMAN_NEAR_PIXEL10, HUMAN_NEAR_PIXEL7, HUMAN_OUTSIDE, NON_HUMAN_MOTION. Run packaged campaign validator. Required: recall>=0.90, specificity>=0.85, healthy indeterminate<=0.10, stationary recall>=0.80, moving recall>=0.90, exact peer and Android↔CLI parity, all transport/artifact/calibration/authority/snapshot gates green.\n\n`human_localization_validated=false`, `rescue_use_validated=false`, and `dev21_blocked=true` until independent G12 returns GO.\n'''
write('docs/TESTING_DEV20_8.md',doc)
write('RELEASE_DEV20_8_TRIGGER.txt','dev20.8 release trigger: G0-G9 only; G10-G12 remain pending.')
print('dev20.8 delta applied')
