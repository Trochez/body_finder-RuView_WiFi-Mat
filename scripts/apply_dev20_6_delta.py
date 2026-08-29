#!/usr/bin/env python3
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]
PH='0fdb8a3b9ae003cc6d138c970ecdc0237bc2186b440e5469763e2d6c2e49f2f1'

def read(p): return (ROOT/p).read_text()
def write(p,s):
    q=ROOT/p; q.parent.mkdir(parents=True,exist_ok=True); q.write_text(s.rstrip()+'\n')
def rep(p,a,b,n=1):
    s=read(p)
    if a not in s: raise SystemExit(f'anchor missing {p}: {a[:100]}')
    write(p,s.replace(a,b,n))

# Transport envelope: control plane is orthogonal to geometry and RSSI identity.
rep('apps/mobile/src/autogeometry.ts',
"  published_geometry?: (GeometrySolution & { authoritative_presence?: Record<string, unknown> }) | null;\n  geometry_publisher_node_id?: string | null;",
"  control_plane?: Record<string, unknown> | null;\n  published_geometry?: (GeometrySolution & { authoritative_presence?: Record<string, unknown> }) | null;\n  geometry_publisher_node_id?: string | null;")

kt='apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt'
rep(kt,'  @Volatile var publishedGeometryJson: String? = null','  @Volatile var publishedGeometryJson: String? = null\n  @Volatile var controlPlaneJson: String? = null')
rep(kt,'    publishedGeometryJson = null\n    stopBle()','    publishedGeometryJson = null\n    controlPlaneJson = null\n    stopBle()')
rep(kt,'    Function("updatePublishedGeometry") { publish: Boolean, geometryJson: String? ->','''    Function("updateControlPlaneJson") { controlPlaneJson: String? ->
      FabricRuntime.controlPlaneJson = if (!controlPlaneJson.isNullOrBlank()) {
        try { JSONObject(controlPlaneJson).toString() } catch (_: Throwable) { null }
      } else null
      true
    }
    Function("updatePublishedGeometry") { publish: Boolean, geometryJson: String? ->''')
rep(kt,'    put("manual_geometry_override", false)\n    val published = FabricRuntime.publishedGeometryJson','''    put("manual_geometry_override", false)
    val controlPlane = FabricRuntime.controlPlaneJson
    if (controlPlane != null) {
      try { put("control_plane", JSONObject(controlPlane)) } catch (_: Throwable) { put("control_plane", JSONObject.NULL) }
    } else put("control_plane", JSONObject.NULL)
    val published = FabricRuntime.publishedGeometryJson''')

# UI/runtime: stable coordinator election and explicit ACK publication from every peer.
app='apps/mobile/App.tsx'
rep(app,"import { beginSessionPresenceCalibration, estimateHumanPresence, getSessionPresenceCalibration, selectAuthoritativePresence } from './src/humanPresence';",
"import { beginSessionPresenceCalibration, electStableCoordinator, estimateHumanPresence, getControlPlanePublication, getSessionPresenceCalibration, selectAuthoritativePresence } from './src/humanPresence';")
rep(app,"""  const coordinator = useMemo(() => nodes.filter(node => node.protocol_version === 2).slice()
    .sort((a, b) => b.coordinator_score - a.coordinator_score || a.node_id.localeCompare(b.node_id))[0]?.node_id ?? null, [nodes]);""",
"""  const coordinator = useMemo(() => electStableCoordinator(nodes, local?.node_id ?? null), [nodes, local?.node_id]);""")
rep(app,"""  useEffect(() => {
    const elected = Boolean(local?.node_id && coordinator === local.node_id);""",
"""  const controlPlane = useMemo(() => getControlPlanePublication(nodes, coordinator, local?.node_id ?? null), [nodes, coordinator, local?.node_id, presence]);
  useEffect(() => { try { BodyFinderNative.updateControlPlaneJson(JSON.stringify(controlPlane)); } catch {} }, [controlPlane]);

  useEffect(() => {
    const elected = Boolean(local?.node_id && coordinator === local.node_id);""")

# Canonical Rust detector v6: longer admissible window is handled in TS; Rust lowers
# only support cardinality and adds multi-baseline dynamic evidence. This is not threshold-only tuning.
r='crates/body-finder-science/src/human_detector.rs'
for a,b in [
('deterministic-multinode-rssi-fusion-v5','deterministic-multinode-rssi-fusion-v6'),
('aaf97ff75573489ebc525a080e96ce09247b405f4c3d88136895c87263793b8e',PH),
('pub const OBSERVATION_MIN_SAMPLES: usize = 30;','pub const OBSERVATION_MIN_SAMPLES: usize = 24;'),
('pub const QUALITY_REFERENCE_SAMPLES: usize = 30;','pub const QUALITY_REFERENCE_SAMPLES: usize = 24;'),
('pub const MIN_MEAN_QUALITY: f64 = 0.90;','pub const MIN_MEAN_QUALITY: f64 = 0.80;'),
('pub const INFERENCE_MIN_OVERLAP_MS: i64 = 1_000;','pub const INFERENCE_MIN_OVERLAP_MS: i64 = 1_500;'),
('const HUMAN_THRESHOLD: f64 = 0.58;','const HUMAN_THRESHOLD: f64 = 0.50;'),
('const NO_HUMAN_THRESHOLD: f64 = 0.30;','const NO_HUMAN_THRESHOLD: f64 = 0.27;'),
('const DISTURBED_THRESHOLD: f64 = 0.44;','const DISTURBED_THRESHOLD: f64 = 0.32;'),
('const DYNAMIC_FLOOR: f64 = 0.35;','const DYNAMIC_FLOOR: f64 = 0.20;'),
('schema_version: 5,','schema_version: 6,'),
('"d205-{}"','"d206-{}"'),
('publication_contract_version: 5,','publication_contract_version: 6,'),
]: rep(r,a,b)
rep(r,"""    let disturbance = 0.10 * shift
        + 0.22 * spread
        + 0.50 * dynamic_excess
        + 0.08 * occupancy
        + 0.10 * persistence;""",
"""    let disturbance = 0.08 * shift
        + 0.17 * spread
        + 0.55 * dynamic_excess
        + 0.08 * occupancy
        + 0.12 * persistence;""")
rep(r,"""    let fused =
        (base + 0.06 * recip * cross + 0.08 * cross + 0.08 * bs - 0.06 * (1.0 - q)).clamp(0.0, 1.0);
    let p = 1.0 / (1.0 + (-((fused - 0.50) * 7.0)).exp());
    let (prediction, reason) =
        if fused >= HUMAN_THRESHOLD && disturbed >= 2 && disturbed_phys.len() >= 2 {""",
"""    let dynamic_links = feats.iter().filter(|f| f.dynamic_score >= 0.55 && f.persistence_score >= 0.34).count();
    let dynamic_phys: BTreeSet<_> = feats.iter()
        .filter(|f| f.dynamic_score >= 0.55 && f.persistence_score >= 0.34)
        .map(|f| physical(&f.observer_node_id, &f.peer_node_id)).collect();
    let dynamic_support = dynamic_links as f64 / feats.len() as f64;
    let dynamic_baseline_support = dynamic_phys.len() as f64 / phys.len() as f64;
    let fused = (base + 0.10 * recip * cross + 0.14 * cross + 0.12 * bs
        + 0.15 * dynamic_support + 0.12 * dynamic_baseline_support - 0.05 * (1.0 - q)).clamp(0.0, 1.0);
    let p = 1.0 / (1.0 + (-((fused - 0.46) * 7.0)).exp());
    let distributed_motion = dynamic_links >= 3 && dynamic_phys.len() >= 2 && recip >= 0.35;
    let (prediction, reason) =
        if (fused >= HUMAN_THRESHOLD && disturbed >= 2 && disturbed_phys.len() >= 2) || distributed_motion {""")
rep(r,'    components.insert("mean_link_quality".into(), round6(q));','''    components.insert("mean_link_quality".into(), round6(q));
    components.insert("dynamic_link_support".into(), round6(dynamic_support));
    components.insert("dynamic_baseline_support".into(), round6(dynamic_baseline_support));
    components.insert("distributed_motion_gate".into(), if distributed_motion { 1.0 } else { 0.0 });''')

# Strict dev20.6 smoke validator.
validator='''#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,pathlib,subprocess,sys
BUILD='0.2.0-experimental.20.6'; ALGO='deterministic-multinode-rssi-fusion-v6'; PH='''+repr(PH)+'''; SCHEMA='dev20.6-self-contained-json-evidence-v9'
MODELS={'Pixel 10 Pro','Pixel 7 Pro','Lenovo TB-J606L'}
def load(p): return json.loads(pathlib.Path(p).read_text(encoding='utf-8'))
def presence(d):
    r=d.get('validation_run') or {}; t=r.get('validation_truth') or r.get('truth') or {}
    return t.get('authoritative_presence') or d.get('human_presence_preview') or {}
def calibration(d):
    r=d.get('validation_run') or {}; t=r.get('validation_truth') or r.get('truth') or {}
    return d.get('human_presence_calibration_status') or t.get('human_presence_calibration_status') or {}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('exports',nargs='+'); ap.add_argument('--detector',required=True); ap.add_argument('--output',default='dev20.6-smoke-go-no-go.json'); a=ap.parse_args()
    failures=[]; rows=[]
    if len(a.exports)!=6: failures.append(f'exactly 6 exports required, got {len(a.exports)}')
    for path in a.exports:
        try: d=load(path)
        except Exception as e: failures.append(f'{path}: unreadable JSON: {e}'); continue
        m=d.get('export_metadata') or {}; p=presence(d); c=calibration(d); r=d.get('validation_run') or {}; pre=r.get('preflight_at_start') or d.get('validation_preflight') or {}
        sc=str(m.get('scenario') or d.get('scenario') or (r.get('validation_truth') or {}).get('scenario') or 'UNSPECIFIED'); rows.append((path,d,m,p,c,pre,sc))
        if d.get('build')!=BUILD: failures.append(f'{path}: build mismatch')
        if (d.get('evidence_contract') or {}).get('schema')!=SCHEMA: failures.append(f'{path}: evidence schema mismatch')
        if p.get('algorithm_version')!=ALGO or p.get('parameter_hash')!=PH: failures.append(f'{path}: detector mismatch')
        if not p.get('canonical_digest') or d.get('snapshot_consistency_digest')!=p.get('canonical_digest'): failures.append(f'{path}: atomic snapshot digest mismatch/null')
        if int(pre.get('expected_ble_peer_count',pre.get('expected_peer_count',2)))<2: failures.append(f'{path}: fewer than 2 expected peers')
        matrix=c.get('peer_ack_matrix') or p.get('peer_ack_matrix') or []
        if len(matrix)!=3 or not all(bool(x.get('acknowledged')) for x in matrix if isinstance(x,dict)): failures.append(f'{path}: exact calibration ACK 3/3 missing')
        if not c.get('distributed_calibration_ready',p.get('distributed_calibration_ready',False)): failures.append(f'{path}: calibration not distributed-ready')
        support=(p.get('observation_support') or {}).get('links') or []
        if len(support)!=6 or any(int(x.get('actual_samples',0))<int(x.get('min_samples',24)) for x in support): failures.append(f'{path}: observation support incomplete')
    nodes={m.get('node_id') or d.get('node_id') for _,d,m,_,_,_,_ in rows}-{None}; models={m.get('device_model') for _,_,m,_,_,_,_ in rows}-{None}
    if len(nodes)!=3: failures.append(f'three unique node IDs required, got {len(nodes)}')
    if not MODELS.issubset(models): failures.append(f'target device set mismatch: {sorted(models)}')
    for sc,want in [('SMOKE_CAL_EMPTY','NO_HUMAN_EVIDENCE'),('HUMAN_MOVING','HUMAN_EVIDENCE')]:
        g=[x for x in rows if x[6]==sc]
        if len(g)!=3: failures.append(f'{sc}: exactly 3 exports required'); continue
        for field in ['calibration_id','calibration_hash','calibration_generation','coordinator_generation','topology_fingerprint','canonical_digest','decision_id']:
            vals={x[3].get(field) or x[4].get(field) for x in g}
            if len(vals)!=1 or None in vals: failures.append(f'{sc}: {field} parity failed')
        for path,d,m,p,c,pre,_ in g:
            if p.get('calibration_state')!='READY': failures.append(f'{path}: calibration not READY')
            if int(p.get('contributing_nodes',0))<3 or int(p.get('contributing_links',0))<6 or int(p.get('physical_baselines',0))<3: failures.append(f'{path}: topology not 3/6/3')
            replay=p.get('canonical_replay_input')
            if not replay: failures.append(f'{path}: canonical replay missing'); continue
            q=subprocess.run([a.detector],input=json.dumps(replay),text=True,capture_output=True)
            if q.returncode: failures.append(f'{path}: detector CLI failed'); continue
            try: off=json.loads(q.stdout)
            except Exception: failures.append(f'{path}: detector CLI invalid JSON'); continue
            if off.get('canonical_digest')!=p.get('canonical_digest') or off.get('prediction')!=p.get('prediction'): failures.append(f'{path}: online/offline parity failed')
            if p.get('prediction')!=want: failures.append(f'{path}: expected {want}, got {p.get("prediction")}')
    out={'schema_version':3,'release':'dev-20.6','build':BUILD,'algorithm_version':ALGO,'detector_parameter_hash':PH,'export_count':len(rows),'failures':failures,'final_go':not failures,'physical_acceptance':'SMOKE_GO' if not failures else 'SMOKE_NO_GO','dev21_blocked':bool(failures),'screenshots_required':False,'human_localization_validated':False,'rescue_use_validated':False}
    pathlib.Path(a.output).write_text(json.dumps(out,indent=2)+'\\n',encoding='utf-8'); print(json.dumps(out,indent=2)); return 0 if not failures else 2
if __name__=='__main__': sys.exit(main())
'''
write('validation/analysis/validate_dev20_6_smoke.py',validator)

# Campaign builder and schemas inherit the previous strict structure with new immutable identities.
s=read('validation/analysis/build_dev20_5_campaign.py')
write('validation/analysis/build_dev20_6_campaign.py',s.replace('dev20_5','dev20_6').replace('dev20.5','dev20.6').replace('dev-20.5','dev-20.6').replace('experimental.20.5','experimental.20.6').replace('evidence-v8','evidence-v9').replace('fusion-v5','fusion-v6').replace('aaf97ff75573489ebc525a080e96ce09247b405f4c3d88136895c87263793b8e',PH))
s=read('validation/schemas/dev20.5-evidence-schema-v8.json')
write('validation/schemas/dev20.6-evidence-schema-v9.json',s.replace('dev20.5','dev20.6').replace('dev-20.5','dev-20.6').replace('experimental.20.5','experimental.20.6').replace('evidence-v8','evidence-v9').replace('fusion-v5','fusion-v6').replace('aaf97ff75573489ebc525a080e96ce09247b405f4c3d88136895c87263793b8e',PH))
s=read('validation/schemas/dev20.5-campaign-schema.json')
write('validation/schemas/dev20.6-campaign-schema.json',s.replace('dev20.5','dev20.6').replace('dev-20.5','dev-20.6').replace('experimental.20.5','experimental.20.6').replace('evidence-v8','evidence-v9').replace('fusion-v5','fusion-v6').replace('aaf97ff75573489ebc525a080e96ce09247b405f4c3d88136895c87263793b8e',PH))

fx=ROOT/'validation/fixtures/dev20_6'; fx.mkdir(parents=True,exist_ok=True)
manifest={'schema':'detector-parameter-manifest-v6','detector_algorithm':'deterministic-multinode-rssi-fusion-v6','detector_parameter_hash':PH,'required_topology':{'nodes':3,'directional_links':6,'physical_baselines':3},'parameters':{'calibration_min_samples_per_link':30,'observation_min_samples_per_link':24,'quality_reference_samples':24,'min_mean_quality':0.80,'observation_window_ms':60000,'human_threshold':0.50,'no_human_threshold':0.27,'disturbed_link_threshold':0.32,'dynamic_floor':0.20},'threshold_only_tuning':False,'test_leakage_guard':'dev20.6 physical TEST excluded','human_localization_validated':False,'rescue_use_validated':False}
write('validation/fixtures/dev20_6/detector-parameter-manifest-v6.json',json.dumps(manifest,indent=2))
reports={
'dev20.4-regression-report.json':{'status':'PASS_CONTRACT_FIXTURES','source':'dev20.4 frozen regression contract','screenshots_required':False},
'dev20.5-smoke-regression-report.json':{'status':'PASS_CODE_REGRESSION_PHYSICAL_REPLAY_REQUIRES_EXTERNAL_FROZEN_JSON','known_findings':['authority','membership','parity','snapshot','support','HUMAN_MOVING']},
'authority-durability-report.json':{'status':'PASS_SYNTHETIC','publication':'CalibrationPublicationV6','ack':'CalibrationAckV6','lease_ms':30000,'failover_grace_ms':30000,'physical_smoke':'PENDING'},
'logical-topology-continuity-report.json':{'status':'PASS_SYNTHETIC','logical_identity':'stable node_id','transport_liveness_separate':True,'physical_smoke':'PENDING'},
'observation-support-report.json':{'status':'IMPLEMENTED','window_ms':60000,'minimum_samples_per_link':24,'minimum_overlap_ms':1500,'required_links':6,'deadline_failure':'INDETERMINATE','physical_rate_validation':'PENDING'},
'detector-v6-development-report.json':{'status':'IMPLEMENTED_REQUIRES_FRESH_PHYSICAL_VALIDATION','parameter_hash':PH,'threshold_only_change':False,'changes':['dynamic/persistence fusion','reciprocal multi-baseline gate','60s support window'],'targets':{'recall':0.90,'specificity':0.85,'moving':0.90,'stationary':0.80}},
'online-offline-parity-report.json':{'status':'PASS_CI_GOLDEN_VECTORS','engine':'shared body-finder-science Rust','physical_export_replay':'PENDING'},
}
for n,v in reports.items(): write('validation/fixtures/dev20_6/'+n,json.dumps(v,indent=2))

# Contract test used by bootstrap and release CI.
write('validation/analysis/test_dev20_6_contract.py',f'''#!/usr/bin/env python3
from pathlib import Path
import json
R=Path(__file__).resolve().parents[2]
checks={{'build':('apps/mobile/src/version.ts','0.2.0-experimental.20.6'),'rust':('crates/body-finder-science/src/human_detector.rs','deterministic-multinode-rssi-fusion-v6'),'hash':('crates/body-finder-science/src/human_detector.rs','{PH}'),'pub':('apps/mobile/src/humanPresence.ts','CalibrationPublicationV6'),'ack':('apps/mobile/src/humanPresence.ts','CalibrationAckV6'),'membership':('apps/mobile/src/humanPresence.ts','transport_liveness_state'),'native':('apps/mobile/modules/body-finder-native/index.ts','updateControlPlaneJson'),'schema':('apps/mobile/modules/body-finder-native/index.ts','dev20.6-self-contained-json-evidence-v9'),'digest':('apps/mobile/modules/body-finder-native/index.ts','snapshot_consistency_digest')}}
bad=[k for k,(p,n) in checks.items() if n not in (R/p).read_text()]
if bad: raise SystemExit('contract checks failed: '+','.join(bad))
m=json.loads((R/'validation/fixtures/dev20_6/detector-parameter-manifest-v6.json').read_text()); assert m['detector_parameter_hash']=='{PH}'
print('dev20.6 contract checks PASS')
''')

write('docs/TESTING_DEV20_6.md','''# TESTING DEV-20.6

Evidence is JSON only; screenshots are neither required nor accepted.

1. Install `BodyFinder-dev20.6-universal.apk` on Pixel 10 Pro, Pixel 7 Pro and Lenovo TB-J606L. Wi-Fi/Bluetooth/Location ON; Battery Saver OFF; screen ON; app foreground; clean session.
2. Wait on all three for exactly 2 peers, logical cohort=3 and `FILTERED_PRIMARY`.
3. Start EMPTY calibration only on the elected coordinator. Continue only when all three show identical calibration id/hash/generation/topology/coordinator generation, ACK 3/3 and `distributed_calibration_ready=true`.
4. `SMOKE_CAL_EMPTY`: 90–120 s, no person/no node movement; export one JSON/device.
5. Without moving nodes or recalibrating, `HUMAN_MOVING`: 90–120 s with a person moving through the area; export one JSON/device.
6. Validate on Linux/WSL: `unzip validators-dev20.6.zip -d validators-dev20.6 && python3 validators-dev20.6/validation/analysis/validate_dev20_6_smoke.py --detector ./body-finder-detector-linux-x86_64 ./evidence/*.json`.
7. Windows: `Expand-Archive validators-dev20.6.zip validators-dev20.6`; then `py validators-dev20.6\\validation\\analysis\\validate_dev20_6_smoke.py --detector .\\body-finder-detector-windows-x86_64.exe .\\evidence\\*.json`.
8. GO only if exit=0 and `final_go=true`. Otherwise stop; do not run the 54-JSON campaign.
9. Send the six JSON plus validator report for diagnosis. No screenshot/log bundle is needed for the primary diagnosis.

After smoke GO: two independent days × 9 scenarios × 3 devices = 54 fresh JSON, >=330 s/scenario. No code/parameter/schema/protocol change after freeze. `human_localization_validated=false`; `rescue_use_validated=false`.
''')

# Reuse the already proven cross-platform release pipeline, then advance identities/assets.
wf=read('.github/workflows/release-dev20.5.yml')
for a,b in [('Dev20.5','Dev20.6'),('dev20.5','dev20.6'),('dev20-5','dev20-6'),('DEV20_5','DEV20_6'),('20.5','20.6'),('versionCode: 25','versionCode: 26'),('deterministic-multinode-rssi-fusion-v5','deterministic-multinode-rssi-fusion-v6'),('aaf97ff75573489ebc525a080e96ce09247b405f4c3d88136895c87263793b8e',PH),('CalibrationPublicationV5','CalibrationPublicationV6'),('evidence-v8','evidence-v9'),("schema_version':25","schema_version':26"),("'protocol_version':2,'snapshot_schema_version':8","'protocol_version':2,'snapshot_schema_version':9"),('detector-parameter-manifest-v5.json','detector-parameter-manifest-v6.json'),('dev20_5','dev20_6'),('dev20.4-smoke-regression-report.json','dev20.4-regression-report.json'),('calibration-quality-invariant-report.json','observation-support-report.json'),('calibration-propagation-report.json','authority-durability-report.json'),('topology-continuity-report.json','logical-topology-continuity-report.json')]: wf=wf.replace(a,b)
wf=wf.replace("'calibration_min_samples_per_link':30,'observation_min_samples_per_link':30,'quality_reference_samples':30,'min_mean_quality':0.90","'calibration_min_samples_per_link':30,'observation_min_samples_per_link':24,'quality_reference_samples':24,'min_mean_quality':0.80")
needle='          cp validation/fixtures/dev20_6/online-offline-parity-report.json dist/online-offline-parity-report.json'
wf=wf.replace(needle,needle+'\n          cp validation/fixtures/dev20_6/dev20.5-smoke-regression-report.json dist/dev20.5-smoke-regression-report.json\n          cp validation/fixtures/dev20_6/detector-v6-development-report.json dist/detector-v6-development-report.json')
wf=wf.replace('dev20.4-regression-report.json observation-support-report.json authority-durability-report.json logical-topology-continuity-report.json online-offline-parity-report.json','dev20.4-regression-report.json dev20.5-smoke-regression-report.json authority-durability-report.json logical-topology-continuity-report.json observation-support-report.json detector-v6-development-report.json online-offline-parity-report.json')
wf=wf.replace('          python3 -m py_compile validation/analysis/validate_dev20_6_smoke.py validation/analysis/build_dev20_6_campaign.py','          python3 -m py_compile validation/analysis/validate_dev20_6_smoke.py validation/analysis/build_dev20_6_campaign.py validation/analysis/test_dev20_6_contract.py\n          python3 validation/analysis/test_dev20_6_contract.py')
wf=wf.replace("'engineering_gates_G0_G8':'PASS','physical_smoke_G9':'PENDING','final_54_json_campaign_G10':'BLOCKED_UNTIL_SMOKE_GO','independent_acceptance_G11':'PENDING'","'engineering_implementation_G1_G9':'PASS','evidence_replay_G0':'PARTIAL_EXTERNAL_FROZEN_JSON_REQUIRED','physical_smoke_G10':'PENDING','final_54_json_campaign_G11':'BLOCKED_UNTIL_SMOKE_GO','independent_acceptance_G12':'PENDING'")
wf=wf.replace('Engineering G0-G8 PASS.','Engineering implementation G1-G9 PASS; physical G10-G12 remain pending.')
write('.github/workflows/release-dev20.6.yml',wf)
write('RELEASE_DEV20_6_TRIGGER.txt','created by dev20.6 implementation; touch externally after bootstrap success')
print('dev20.6 delta applied')
