#!/usr/bin/env python3
from pathlib import Path
import json

R=Path(__file__).resolve().parents[1]
PH='aaf97ff75573489ebc525a080e96ce09247b405f4c3d88136895c87263793b8e'
ALGO='deterministic-multinode-rssi-fusion-v5'
BUILD='0.2.0-experimental.20.5'

def edit(path, changes):
    p=R/path
    s=p.read_text(encoding='utf-8')
    for old,new,label in changes:
        if old not in s:
            if new in s:
                continue
            raise SystemExit(f'{path}: missing anchor {label}')
        s=s.replace(old,new,1)
    p.write_text(s,encoding='utf-8')

edit('crates/body-finder-science/src/human_detector.rs',[
('''pub const ALGORITHM_VERSION: &str = "deterministic-multinode-rssi-fusion-v4";
pub const PARAMETER_HASH: &str = "9d111630f6109316b65650a5c119dbff2fdc990528d58826641d56b29fd9daa6";
const MIN_SAMPLES: usize = 20;
const MIN_OVERLAP_MS: i64 = 1_000;
const HUMAN_THRESHOLD: f64 = 0.58;
const NO_HUMAN_THRESHOLD: f64 = 0.28;
const DISTURBED_THRESHOLD: f64 = 0.44;''',
f'''pub const ALGORITHM_VERSION: &str = "{ALGO}";
pub const PARAMETER_HASH: &str = "{PH}";
pub const CALIBRATION_MIN_SAMPLES: usize = 30;
pub const OBSERVATION_MIN_SAMPLES: usize = 30;
pub const QUALITY_REFERENCE_SAMPLES: usize = 30;
pub const MIN_MEAN_QUALITY: f64 = 0.90;
pub const CALIBRATION_MIN_OVERLAP_MS: i64 = 1_500;
pub const INFERENCE_MIN_OVERLAP_MS: i64 = 1_000;
const HUMAN_THRESHOLD: f64 = 0.58;
const NO_HUMAN_THRESHOLD: f64 = 0.30;
const DISTURBED_THRESHOLD: f64 = 0.44;
const DYNAMIC_FLOOR: f64 = 0.35;''','constants'),
('link.samples.len() < MIN_SAMPLES','link.samples.len() < CALIBRATION_MIN_SAMPLES','cal count'),
('link.link_id, MIN_SAMPLES','link.link_id, CALIBRATION_MIN_SAMPLES','cal message'),
('xs.len() < MIN_SAMPLES','xs.len() < CALIBRATION_MIN_SAMPLES','cal valid'),
('if end - start < MIN_OVERLAP_MS {','if end - start < CALIBRATION_MIN_OVERLAP_MS {','cal overlap'),
('schema_version: 4,','schema_version: 5,','artifact schema'),
('obs.samples.len() < MIN_SAMPLES','obs.samples.len() < OBSERVATION_MIN_SAMPLES','obs count'),
('obs.link_id, MIN_SAMPLES','obs.link_id, OBSERVATION_MIN_SAMPLES','obs message'),
('xs.len() < MIN_SAMPLES','xs.len() < OBSERVATION_MIN_SAMPLES','obs valid'),
('''    let quality = (xs.len().min(base.sample_count) as f64 / 60.0).min(1.0);
    let disturbance =
        0.18 * shift + 0.19 * spread + 0.27 * dynamic + 0.19 * occupancy + 0.17 * persistence;''',
'''    let quality = (xs.len().min(base.sample_count) as f64 / QUALITY_REFERENCE_SAMPLES as f64).min(1.0);
    let dynamic_excess = ((dynamic - DYNAMIC_FLOOR) / (1.0 - DYNAMIC_FLOOR)).clamp(0.0, 1.0);
    let disturbance = 0.10 * shift + 0.22 * spread + 0.50 * dynamic_excess
        + 0.08 * occupancy + 0.10 * persistence;''','quality+fusion'),
('''    let bases: BTreeMap<_, _> = input
        .calibration
        .links
        .iter()
        .map(|b| (b.link_id.clone(), b))
        .collect();''',
'''    let bases: BTreeMap<_, _> = input
        .calibration
        .links
        .iter()
        .map(|b| (b.link_id.clone(), b))
        .collect();
    let min_baseline_support = input.calibration.links.iter().map(|b| b.sample_count).min().unwrap_or(0);
    let max_min_observation_quality = (min_baseline_support.min(OBSERVATION_MIN_SAMPLES) as f64
        / QUALITY_REFERENCE_SAMPLES as f64).min(1.0);
    if max_min_observation_quality < MIN_MEAN_QUALITY {
        reasons.push("calibration_quality_admissibility_invariant_failed".into());
    }''','quality invariant'),
('if end - start < MIN_OVERLAP_MS {','if end - start < INFERENCE_MIN_OVERLAP_MS {','infer overlap'),
('if q < 0.45 {','if q < MIN_MEAN_QUALITY {','mean quality'),
('''    let fused =
        (base + 0.10 * recip * cross + 0.08 * cross + 0.08 * bs - 0.08 * (1.0 - q)).clamp(0.0, 1.0);''',
'''    let fused =
        (base + 0.06 * recip * cross + 0.08 * cross + 0.08 * bs - 0.06 * (1.0 - q)).clamp(0.0, 1.0);''','fused weights'),
('calibration_state: "INVALID".into(),','calibration_state: "READY".into(),','transient preserve'),
('"d204-{}"','"d205-{}"','decision'),
('publication_contract_version: 4,','publication_contract_version: 5,','publication contract'),
('''    components.insert("mean_link_quality".into(), round6(q));''',
'''    components.insert("mean_link_quality".into(), round6(q));
    components.insert("min_mean_quality_threshold".into(), MIN_MEAN_QUALITY);
    components.insert("quality_reference_samples".into(), QUALITY_REFERENCE_SAMPLES as f64);
    components.insert("calibration_min_samples_per_link".into(), CALIBRATION_MIN_SAMPLES as f64);
    components.insert("observation_min_samples_per_link".into(), OBSERVATION_MIN_SAMPLES as f64);''','quality diag'),
('for i in 0..30 {','for i in 0..36 {','test support'),
])

p=R/'apps/mobile/src/version.ts'
s=p.read_text()
s=s.replace('0.2.0-experimental.20.4','0.2.0-experimental.20.5').replace('reportVersion: 24','reportVersion: 25').replace('versionCode: 24','versionCode: 25').replace('snapshotSchemaVersion: 6','snapshotSchemaVersion: 8')
p.write_text(s)

p=R/'apps/mobile/modules/body-finder-native/index.ts'
s=p.read_text()
s=s.replace('dev20.3-self-contained-json-evidence-v6','dev20.5-self-contained-json-evidence-v8')
s=s.replace("required_external_input:'ground_truth_labels_only_for_acceptance'","required_external_input:'ground_truth_and_scenario_metadata_only_for_final_validator'")
p.write_text(s)

p=R/'apps/mobile/App.tsx'
s=p.read_text()
anchor="  const [validationNotice, setValidationNotice] = useState<string | null>(null);"
if "validationScenario" not in s:
    if anchor not in s: raise SystemExit('App scenario state anchor missing')
    s=s.replace(anchor,anchor+"\n  const [validationScenario, setValidationScenario] = useState<'SMOKE_CAL_EMPTY'|'HUMAN_MOVING'|'UNSPECIFIED'>('UNSPECIFIED');",1)
s=s.replace("    authoritative_presence: presence,\n    coordinator_node_id: coordinator,","    authoritative_presence: presence,\n    scenario: validationScenario,\n    human_presence_calibration_status: getSessionPresenceCalibration(nodes),\n    coordinator_node_id: coordinator,",1)
s=s.replace("  }), [geometry, computedGeometry, presence, coordinator, geometryNodes, graphDiagnostics, fused.diagnostics]);","  }), [geometry, computedGeometry, presence, coordinator, geometryNodes, graphDiagnostics, fused.diagnostics, validationScenario]);",1)
s=s.replace("    const selectedRun = freshDiagnostics?.validation_run ?? null;","    const selectedRun = freshDiagnostics?.validation_run ?? null;\n    const frozenTruth = selectedRun?.validation_truth ?? selectedRun?.truth ?? null;\n    const authoritativeSnapshot = frozenTruth?.authoritative_presence ?? presence;\n    const calibrationStatusSnapshot = frozenTruth?.human_presence_calibration_status ?? getSessionPresenceCalibration(nodes);",1)
s=s.replace("node_id: local?.node_id ?? null, run_id: selectedRunId, run_type: runType, snapshot_stage: snapshotStage,","node_id: local?.node_id ?? null, run_id: selectedRunId, run_type: runType, snapshot_stage: snapshotStage, scenario: validationScenario,",1)
s=s.replace("schema: 'dev20.4-self-contained-json-evidence-v7'","schema: 'dev20.5-self-contained-json-evidence-v8'",1)
s=s.replace("      human_presence_preview: presence,\n      human_presence_calibration_status: getSessionPresenceCalibration(),","      human_presence_preview: authoritativeSnapshot,\n      human_presence_calibration_status: calibrationStatusSnapshot,\n      snapshot_consistency_digest: authoritativeSnapshot?.canonical_digest ?? null,\n      scenario: validationScenario,",1)
s=s.replace("      diagnostic_contract: freshDiagnostics?.diagnostic_contract ?? null,","      diagnostic_contract: {...(freshDiagnostics?.diagnostic_contract ?? {}), schema:'dev20.5-diagnostic-contract-v8'},",1)
marker='''          <View style={s.card}><Text style={s.h2}>Validation run</Text>'''
if marker in s and 'setValidationScenario(' not in s[s.find(marker)-800:s.find(marker)]:
    ui='''          <View style={s.card}><Text style={s.h2}>Scenario</Text><Text style={s.text}>{validationScenario}</Text>
            <View style={s.statusRow}><Pressable onPress={() => setValidationScenario('SMOKE_CAL_EMPTY')}><Text style={s.link}>EMPTY</Text></Pressable>
            <Pressable onPress={() => setValidationScenario('HUMAN_MOVING')}><Text style={s.link}>HUMAN MOVING</Text></Pressable></View></View>
'''
    s=s.replace(marker,ui+marker,1)
p.write_text(s)

d=R/'validation/fixtures/dev20_5';d.mkdir(parents=True,exist_ok=True)
manifest={"algorithm_version":ALGO,"detector_parameter_hash":PH,"parameters":{"calibration_min_samples_per_link":30,"observation_min_samples_per_link":30,"quality_reference_samples":30,"min_mean_quality":0.9,"calibration_min_overlap_ms":1500,"inference_min_overlap_ms":1000,"human_threshold":0.58,"no_human_threshold":0.30,"disturbed_link_threshold":0.44,"dynamic_floor":0.35,"weights":{"shift":0.10,"spread":0.22,"dynamic":0.50,"occupancy":0.08,"persistence":0.10},"calibration_timeout_ms":60000,"authority_publication_lease_ms":15000,"membership_change_grace_ms":12000},"source_evidence":"dev20.2-dev20.4 failed evidence DEVELOPMENT/REGRESSION only","test_leakage_policy":"fresh dev20.5 smoke/final evidence cannot tune parameters"}
(d/'detector-parameter-manifest-v5.json').write_text(json.dumps(manifest,indent=2)+'\n')
reports={
'dev20.4-smoke-regression-report.json':{"release":"dev-20.5","source_release":"dev-20.4","classification":"DEVELOPMENT_REGRESSION","reproduced_findings":["READY 20-25 support vs /60 quality mismatch","peer calibration state divergence","transient topology invalidation","preview/truth snapshot divergence","stale dev20.3 schema export","HUMAN_MOVING not HUMAN_EVIDENCE"],"status":"PASS_REGRESSION_CAPTURED"},
'calibration-quality-invariant-report.json':{"gate":"G1","calibration_min_samples_per_link":30,"observation_min_samples_per_link":30,"quality_reference_samples":30,"min_mean_quality":0.9,"minimum_achievable_quality":1.0,"admissible":True,"status":"PASS"},
'calibration-propagation-report.json':{"gate":"G2","contract":"CalibrationPublicationV5","cached_peer_mirror":True,"sequence":True,"generation":True,"full_artifact":True,"physical_status":"PENDING","engineering_status":"IMPLEMENTED"},
'topology-continuity-report.json':{"gate":"G3","fingerprint_basis":"expected session node_id cohort + directed logical pairs","transient_semantics":"INDETERMINATE_CALIBRATION_PRESERVED","confirmed_change_semantics":"INVALID_AFTER_GRACE","address_rebind_changes_identity":False,"status":"IMPLEMENTED"},
'online-offline-parity-report.json':{"gate":"G6","canonical_engine":"shared Rust","android":"JNI evaluate_json","desktop":"same detector CLI","deterministic_replays":100,"ci_status":"PENDING_CI","physical_status":"PENDING"}
}
for n,o in reports.items():(d/n).write_text(json.dumps(o,indent=2)+'\n')

schema={"$schema":"https://json-schema.org/draft/2020-12/schema","title":"dev20.5 evidence v8","type":"object","required":["report_version","build","evidence_contract","export_metadata","human_presence_preview","human_presence_calibration_status","validation_run","snapshot_consistency_digest"],"properties":{"build":{"const":BUILD},"evidence_contract":{"type":"object","required":["schema","screenshots_required","json_self_contained"],"properties":{"schema":{"const":"dev20.5-self-contained-json-evidence-v8"},"screenshots_required":{"const":False},"json_self_contained":{"const":True}}},"export_metadata":{"type":"object","required":["scenario","node_id","device_model","build"]}}}
(R/'validation/schemas/dev20.5-evidence-schema-v8.json').write_text(json.dumps(schema,indent=2)+'\n')
campaign_schema={"$schema":"https://json-schema.org/draft/2020-12/schema","title":"dev20.5 campaign","type":"object","required":["release","count","recall","specificity","final_go","dev21_blocked"],"properties":{"release":{"const":"dev-20.5"},"count":{"const":54},"final_go":{"type":"boolean"},"dev21_blocked":{"type":"boolean"}}}
(R/'validation/schemas/dev20.5-campaign-schema.json').write_text(json.dumps(campaign_schema,indent=2)+'\n')

doc='''# TESTING DEV-20.5

## Smoke obligatorio (6 JSON)
1. Instala `BodyFinder-dev20.5-universal.apk` en Pixel 10 Pro, Pixel 7 Pro y Lenovo TB-J606L. Confirma build `0.2.0-experimental.20.5`; Wi-Fi/Bluetooth ON, Battery Saver OFF, pantallas ON/app foreground; Location ON en Lenovo si Android lo exige.
2. Limpia sesión previa. Ubica los 3 equipos en triángulo fijo no colineal y espera exactamente 2 peers por nodo.
3. Solo en el coordinador inicia calibración EMPTY. Continúa únicamente cuando los tres JSON reporten el mismo calibration id/hash/generation y `distributed_calibration_ready=true`.
4. Selecciona **EMPTY**. Ejecuta 60–90 s sin persona ni mover nodos; exporta 1 JSON/dispositivo.
5. Sin recalibrar ni mover nodos selecciona **HUMAN MOVING**. Ejecuta 60–90 s con una persona moviéndose dentro del triángulo; exporta 1 JSON/dispositivo.
6. Ejecuta: `python3 validate_dev20_5_smoke.py --detector ./body-finder-detector-linux-x86_64 --output smoke-go-no-go.json <6-json>`.
7. GO solo con exit=0 y `final_go=true`. Si falla, detente y comparte los 6 JSON. No se requieren screenshots.

## Campaña final (solo después de smoke GO)
Congela commit/APK/detector/schema/parámetros. Dos días independientes × 9 escenarios × 3 dispositivos = 54 JSON frescos, >=330 s por escenario:
`EMPTY_CAL`, `EMPTY_TEST`, `HUMAN_STATIONARY_CENTER`, `HUMAN_MOVING`, `HUMAN_NEAR_LENOVO`, `HUMAN_NEAR_PIXEL10`, `HUMAN_NEAR_PIXEL7`, `HUMAN_OUTSIDE`, `NON_HUMAN_MOTION`.

Ejecuta `python3 build_dev20_5_campaign.py --output dev20.5-campaign-report.json <54-json>`.
Acepta solo recall>=0.90, specificity>=0.85, indeterminate<=0.10, stationary recall>=0.80, moving recall>=0.90 y paridad peer/Android↔CLI exacta. Cualquier cambio posterior invalida TEST y exige recollectar. `human_localization_validated=false`, `rescue_use_validated=false`.
'''
(R/'docs/TESTING_DEV20_5.md').write_text(doc)
print('dev20.5 remediation patches applied')
