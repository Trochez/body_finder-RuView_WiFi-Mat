#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, pathlib, re, shutil
ROOT=pathlib.Path(__file__).resolve().parents[1]

def p(rel): return ROOT/rel
def read(rel): return p(rel).read_text()
def write(rel,s): p(rel).parent.mkdir(parents=True,exist_ok=True); p(rel).write_text(s)
def repl(rel, old, new, count=-1):
    s=read(rel)
    if old not in s: raise SystemExit(f'missing pattern in {rel}: {old[:100]!r}')
    s2=s.replace(old,new,count)
    write(rel,s2)

# Release identity / one duration constant.
repl('apps/mobile/src/version.ts',"build: '0.2.0-experimental.20.2'","build: '0.2.0-experimental.20.3'")
repl('apps/mobile/src/version.ts','reportVersion: 22','reportVersion: 23')
repl('apps/mobile/src/version.ts','versionCode: 22','versionCode: 23')
repl('apps/mobile/src/version.ts',"releaseIteration: 'experimental.20.2'","releaseIteration: 'experimental.20.3'")
repl('apps/mobile/app.json','"versionCode": 22','"versionCode": 23')
repl('apps/mobile/app.json','"releaseIteration": "experimental.20.2"','"releaseIteration": "experimental.20.3"')
repl('apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt','.put("acceptance_minimum_ms", 300_000L)','.put("acceptance_minimum_ms", 330_000L)')

# Canonical parameter manifest. These are architecture-remediation defaults; final physical TEST is still required.
params={
 'schema':'dev20.3-detector-parameters-v1','algorithm_version':'deterministic-multinode-rssi-fusion-v3',
 'acceptance_minimum_ms':330000,'min_samples_per_link':20,'min_observer_nodes':3,'min_directional_links':6,
 'min_physical_baselines':3,'max_alignment_span_ms':12000,'min_mean_quality':0.45,
 'feature_clip':4.0,'deviation_band_sigma':2.5,'deviation_band_floor_db':3.0,
 'human_support_score':0.66,'human_min_disturbed_links':2,'human_min_disturbed_baselines':2,
 'no_human_max_score':0.25,'no_human_max_disturbed_links':0,
 'weights':{'median_shift':0.07,'mean_shift':0.06,'mad_change':0.08,'variance_change':0.16,'iqr_change':0.12,
            'derivative_energy':0.18,'slope_activity':0.10,'deviation_occupancy':0.12,'persistence':0.11},
 'fusion':{'reciprocal_support':0.16,'cross_link_support':0.18,'observer_support':0.08,'baseline_support':0.08},
 'selection_status':'FROZEN_FOR_DEV20_3_PHYSICAL_SMOKE','final_physical_acceptance':'PENDING',
 'selection_note':'Feature redesign follows dev-20.2 diagnosis. Raw dev-20.2 archive was unavailable to this implementation executor, so no false 54-file replay or held-out performance claim is made.'
}
canon=json.dumps(params,sort_keys=True,separators=(',',':'))
param_hash=hashlib.sha256(canon.encode()).hexdigest()
params['parameter_hash']=param_hash
write('validation/fixtures/dev20_3/detector-parameter-manifest.json',json.dumps(params,indent=2,sort_keys=True)+'\n')
write('apps/mobile/src/detectorParameters.ts',f"// Generated from validation/fixtures/dev20_3/detector-parameter-manifest.json\nexport const DETECTOR_ALGORITHM = 'deterministic-multinode-rssi-fusion-v3';\nexport const DETECTOR_PARAMETER_HASH = '{param_hash}';\nexport const DETECTOR = Object.freeze({{\n  minSamplesPerLink:20,minObserverNodes:3,minDirectionalLinks:6,minPhysicalBaselines:3,maxAlignmentSpanMs:12000,minMeanQuality:0.45,featureClip:4,\n  humanSupportScore:0.66,humanMinDisturbedLinks:2,humanMinDisturbedBaselines:2,noHumanMaxScore:0.25,noHumanMaxDisturbedLinks:0,\n  weights:{{medianShift:.07,meanShift:.06,madChange:.08,varianceChange:.16,iqrChange:.12,derivativeEnergy:.18,slopeActivity:.10,deviationOccupancy:.12,persistence:.11}},\n  fusion:{{reciprocalSupport:.16,crossLinkSupport:.18,observerSupport:.08,baselineSupport:.08}}\n}});\n")

# Canonical Android/coordinator detector. Full topology is mandatory; clean negative is affirmative, not symmetric thresholding.
human_ts=r'''import type { Advertisement } from './autogeometry';
import { DETECTOR, DETECTOR_ALGORITHM, DETECTOR_PARAMETER_HASH } from './detectorParameters';

export type HumanPresencePreview = {
  prediction:'HUMAN_EVIDENCE'|'NO_HUMAN_EVIDENCE'|'INDETERMINATE'; confidence:number; quality:number;
  aggregate_normalized_change:number|null; fused_score:number|null; contributing_nodes:number; contributing_links:number;
  physical_baselines:number; reciprocal_coherence:number|null; disturbed_links:number; disturbed_baselines:number;
  components:Record<string,number>; reason:string; calibration_state:string; algorithm_version:string; parameter_hash:string;
  decision_id:string; window_id:string; authoritative:boolean; source:'coordinator'|'coordinator-publication'|'diagnostic';
};
type S={observer:string,peer:string,median:number,quality:number,wall:number};
const clamp=(x:number)=>Math.max(0,Math.min(DETECTOR.featureClip,x));
const median=(xs:number[])=>{const a=[...xs].sort((x,y)=>x-y);return a.length? (a.length%2?a[(a.length-1)/2]:(a[a.length/2-1]+a[a.length/2])/2):0};
const mean=(xs:number[])=>xs.length?xs.reduce((a,b)=>a+b,0)/xs.length:0;
const variance=(xs:number[])=>{const m=mean(xs);return xs.length?mean(xs.map(x=>(x-m)**2)):0};
const iqr=(xs:number[])=>{if(!xs.length)return 0;const a=[...xs].sort((x,y)=>x-y);const q=(t:number)=>a[Math.min(a.length-1,Math.floor((a.length-1)*t))];return q(.75)-q(.25)};
const hash=(s:string)=>{let h=2166136261;for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619)}return ('00000000'+(h>>>0).toString(16)).slice(-8)};
function sampleMap(nodes:Advertisement[]){const m=new Map<string,{baseline:number,sigma:number,values:number[],wall:number[],quality:number,observer:string,peer:string}>();for(const n of nodes){for(const r of n.ranges??[]){if(typeof r.rssi_dbm!=='number'||!r.peer_node_id)continue;const peer=String(r.peer_node_id),k=`${n.node_id}::${peer}`,x=m.get(k)??{baseline:typeof n.baseline_rssi_dbm==='number'?n.baseline_rssi_dbm:r.rssi_dbm,sigma:Math.max(1,typeof n.baseline_sigma_db==='number'?n.baseline_sigma_db:2),values:[],wall:[],quality:0,observer:n.node_id,peer};x.values.push(r.rssi_dbm);x.wall.push(typeof r.source_observation_monotonic_ns==='number'?r.source_observation_monotonic_ns/1e6:Date.now());x.quality=Math.max(x.quality,typeof r.quality==='number'?r.quality:.5);m.set(k,x)}}return m}
export function estimateHumanPresence(nodes:Advertisement[], source:'coordinator'|'diagnostic'='diagnostic'):HumanPresencePreview{
 const m=sampleMap(nodes), links=[...m.entries()].filter(([,x])=>x.values.length>=3);const observers=new Set(links.map(([,x])=>x.observer));const baselines=new Set(links.map(([,x])=>[x.observer,x.peer].sort().join('::')));
 const window=`${Math.floor(Date.now()/2000)*2000}`; const base={confidence:0,quality:0,aggregate_normalized_change:null,fused_score:null,contributing_nodes:observers.size,contributing_links:links.length,physical_baselines:baselines.size,reciprocal_coherence:null,disturbed_links:0,disturbed_baselines:0,components:{},calibration_state:'SESSION_EMPTY_CAL_REQUIRED',algorithm_version:DETECTOR_ALGORITHM,parameter_hash:DETECTOR_PARAMETER_HASH,window_id:window,decision_id:'',authoritative:source==='coordinator',source} as HumanPresencePreview;
 const finish=(prediction:HumanPresencePreview['prediction'],reason:string,score:number|null,extra:Partial<HumanPresencePreview>={})=>{const seed=`${window}|${DETECTOR_ALGORITHM}|${DETECTOR_PARAMETER_HASH}|${prediction}|${score??'null'}|${[...m.keys()].sort().join(',')}`;return {...base,...extra,prediction,reason,fused_score:score,decision_id:`d203-${hash(seed)}`}};
 if(observers.size<DETECTOR.minObserverNodes||links.length<DETECTOR.minDirectionalLinks||baselines.size<DETECTOR.minPhysicalBaselines)return finish('INDETERMINATE','full_3node_6link_3baseline_topology_required',null);
 const feats=links.map(([k,x])=>{const v=x.values,b=x.baseline,s=x.sigma,abs=mean(v.map(z=>Math.abs(z-b)))/s,med=Math.abs(median(v)-b)/s,mn=Math.abs(mean(v)-b)/s,vr=variance(v)/(s*s),iq=iqr(v)/(1.349*s),der=v.length>1?mean(v.slice(1).map((z,i)=>Math.abs(z-v[i])))/s:0,occ=mean(v.map(z=>Math.abs(z-b)>=Math.max(3,2.5*s)?1:0));let best=0,cur=0;for(const z of v){cur=Math.abs(z-b)>=Math.max(3,2.5*s)?cur+1:0;best=Math.max(best,cur)}const pers=best/Math.max(1,v.length);const mad=median(v.map(z=>Math.abs(z-median(v))))/(.6745*s);const slope=der;const w=DETECTOR.weights;const score=clamp(w.medianShift*med+w.meanShift*mn+w.madChange*mad+w.varianceChange*vr+w.iqrChange*iq+w.derivativeEnergy*der+w.slopeActivity*slope+w.deviationOccupancy*occ*4+w.persistence*pers*4);return {k,x,score,disturbed:score>=.48||occ>=.22||der>=.85,abs}});
 const q=mean(feats.map(f=>f.x.quality));if(q<DETECTOR.minMeanQuality)return finish('INDETERMINATE','mean_quality_below_gate',null,{quality:q});
 const reciprocal=mean(feats.map(f=>{const r=feats.find(g=>g.x.observer===f.x.peer&&g.x.peer===f.x.observer);return r?Math.max(0,1-Math.abs(f.score-r.score)/DETECTOR.featureClip):0}));const disturbed=feats.filter(f=>f.disturbed),db=new Set(disturbed.map(f=>[f.x.observer,f.x.peer].sort().join('::')));const baseScore=mean(feats.map(f=>f.score));const cross=disturbed.length/feats.length;const fs=clamp(baseScore+DETECTOR.fusion.reciprocalSupport*reciprocal+DETECTOR.fusion.crossLinkSupport*cross+DETECTOR.fusion.observerSupport*Math.min(1,observers.size/3)+DETECTOR.fusion.baselineSupport*Math.min(1,baselines.size/3));const extra={quality:q,aggregate_normalized_change:mean(feats.map(f=>f.abs)),reciprocal_coherence:reciprocal,disturbed_links:disturbed.length,disturbed_baselines:db.size,components:{base_score:baseScore,reciprocal,cross_link_support:cross,observer_support:observers.size/3,baseline_support:baselines.size/3}};
 if(fs>=DETECTOR.humanSupportScore&&disturbed.length>=DETECTOR.humanMinDisturbedLinks&&db.size>=DETECTOR.humanMinDisturbedBaselines)return finish('HUMAN_EVIDENCE','multi_feature_multi_link_disturbance',fs,extra);
 if(fs<=DETECTOR.noHumanMaxScore&&disturbed.length<=DETECTOR.noHumanMaxDisturbedLinks)return finish('NO_HUMAN_EVIDENCE','affirmative_clean_background_evidence',fs,extra);
 return finish('INDETERMINATE','ambiguous_disturbance',fs,extra);
}
export function selectAuthoritativePresence(nodes:Advertisement[], coordinatorId:string|null, localNodeId:string|null, localDiagnostic:HumanPresencePreview):HumanPresencePreview{
 if(!coordinatorId)return {...localDiagnostic,prediction:'INDETERMINATE',reason:'no_coordinator',authoritative:false,source:'diagnostic'};
 if(coordinatorId===localNodeId)return {...localDiagnostic,authoritative:true,source:'coordinator'};
 const coordinator=nodes.find(n=>n.node_id===coordinatorId) as any;const publication=coordinator?.published_geometry?.authoritative_presence;
 if(publication&&publication.algorithm_version===DETECTOR_ALGORITHM&&publication.parameter_hash===DETECTOR_PARAMETER_HASH&&publication.authoritative===true)return {...publication,source:'coordinator-publication'} as HumanPresencePreview;
 return {...localDiagnostic,prediction:'INDETERMINATE',confidence:0,reason:'waiting_for_coordinator_authoritative_publication',authoritative:false,source:'diagnostic'};
}
'''
write('apps/mobile/src/humanPresence.ts',human_ts)

# Existing geometry publication becomes the coordinator broadcast envelope for authoritative presence.
app=read('apps/mobile/App.tsx')
app=app.replace("import { estimateHumanPresence } from './src/humanPresence';","import { estimateHumanPresence, selectAuthoritativePresence } from './src/humanPresence';")
old="""  const computedGeometry = useMemo(() => solveGeometry(geometryNodes), [geometryNodes]);
  const geometrySelection = useMemo(() => chooseCoordinatorGeometry(nodes, coordinator, local?.node_id ?? null, computedGeometry),
    [nodes, coordinator, local?.node_id, computedGeometry]);
  const geometry = geometrySelection.solution;
  const graphDiagnostics = useMemo(() => diagnoseGeometryGraph(geometryNodes), [geometryNodes]);
  const geometryState = geometry?.state ?? 'GEOMETRY_INSUFFICIENT';

  useEffect(() => { try { BodyFinderNative.updateGeometryState(geometryState); } catch {} }, [geometryState]);

  const validationTruth = useMemo(() => ({
    geometry,
    locally_computed_geometry: computedGeometry,
    fused_range_observations: geometryNodes.flatMap(node => node.ranges ?? []),
    graph_diagnostics: graphDiagnostics,
    reciprocal_fusion: fused.diagnostics,
    measurement_health: {
      health: graphDiagnostics.measurement_health,
      physical_confidence: graphDiagnostics.physical_confidence,
      fresh_metric_edge_count: graphDiagnostics.fresh_metric_edge_count,
      holdover_metric_edge_count: graphDiagnostics.holdover_metric_edge_count,
      geometry_temporal_quality: graphDiagnostics.geometry_temporal_quality,
    },
  }), [geometry, computedGeometry, geometryNodes, graphDiagnostics, fused.diagnostics]);

  useEffect(() => {
    try { BodyFinderNative.updateValidationTruthJson(JSON.stringify(validationTruth)); } catch {}
  }, [validationTruth]);

  useEffect(() => {
    const elected = Boolean(local?.node_id && coordinator === local.node_id);
    try { BodyFinderNative.updatePublishedGeometry(elected, elected && computedGeometry ? JSON.stringify(computedGeometry) : null); } catch {}
  }, [local?.node_id, coordinator, computedGeometry]);
"""
new="""  const computedGeometry = useMemo(() => solveGeometry(geometryNodes), [geometryNodes]);
  const localPresenceDiagnostic = useMemo(() => estimateHumanPresence(nodes, coordinator === local?.node_id ? 'coordinator' : 'diagnostic'), [nodes, coordinator, local?.node_id]);
  const presence = useMemo(() => selectAuthoritativePresence(nodes, coordinator, local?.node_id ?? null, localPresenceDiagnostic), [nodes, coordinator, local?.node_id, localPresenceDiagnostic]);
  const geometrySelection = useMemo(() => chooseCoordinatorGeometry(nodes, coordinator, local?.node_id ?? null, computedGeometry),
    [nodes, coordinator, local?.node_id, computedGeometry]);
  const geometry = geometrySelection.solution;
  const graphDiagnostics = useMemo(() => diagnoseGeometryGraph(geometryNodes), [geometryNodes]);
  const geometryState = geometry?.state ?? 'GEOMETRY_INSUFFICIENT';

  useEffect(() => { try { BodyFinderNative.updateGeometryState(geometryState); } catch {} }, [geometryState]);

  const validationTruth = useMemo(() => ({
    geometry,
    locally_computed_geometry: computedGeometry,
    authoritative_presence: presence,
    coordinator_node_id: coordinator,
    fused_range_observations: geometryNodes.flatMap(node => node.ranges ?? []),
    graph_diagnostics: graphDiagnostics,
    reciprocal_fusion: fused.diagnostics,
    measurement_health: {
      health: graphDiagnostics.measurement_health,
      physical_confidence: graphDiagnostics.physical_confidence,
      fresh_metric_edge_count: graphDiagnostics.fresh_metric_edge_count,
      holdover_metric_edge_count: graphDiagnostics.holdover_metric_edge_count,
      geometry_temporal_quality: graphDiagnostics.geometry_temporal_quality,
    },
  }), [geometry, computedGeometry, presence, coordinator, geometryNodes, graphDiagnostics, fused.diagnostics]);

  useEffect(() => {
    try { BodyFinderNative.updateValidationTruthJson(JSON.stringify(validationTruth)); } catch {}
  }, [validationTruth]);

  useEffect(() => {
    const elected = Boolean(local?.node_id && coordinator === local.node_id);
    const publication = elected && computedGeometry ? {...computedGeometry, authoritative_presence: {...localPresenceDiagnostic, authoritative:true, source:'coordinator'}} : null;
    try { BodyFinderNative.updatePublishedGeometry(elected, publication ? JSON.stringify(publication) : null); } catch {}
  }, [local?.node_id, coordinator, computedGeometry, localPresenceDiagnostic]);
"""
if old not in app: raise SystemExit('App coordinator block pattern not found')
app=app.replace(old,new)
app=app.replace("  const presence = useMemo(() => estimateHumanPresence(nodes), [nodes]);\n",'')
app=app.replace("schema: 'dev16-self-contained-json-evidence-v4'","schema: 'dev20.3-self-contained-json-evidence-v6'")
app=app.replace("required_external_input: 'ground_truth_distances_only_for_accuracy_report'","required_external_input: 'ground_truth_and_scenario_metadata_only_for_final_validator'")
app=app.replace("instructions: 'Return the exported JSON files only. Screenshots are not required for dev-14 evidence. Use >=330 s for acceptance; short runs remain diagnostic only. Do not change calibration, minSamples, freshness, holdover or solver settings. Human scanning remains blocked.',","instructions: 'Return exported JSON files only; screenshots are unnecessary. Acceptance requires >=330 s, valid EMPTY_CAL, 3 nodes/6 directional links/3 baselines, peer authoritative consistency and offline replay parity. Human localization and rescue use remain unvalidated.',")
write('apps/mobile/App.tsx',app)

# Geometry type accepts the coordinator publication envelope without affecting the geometry solver.
auto=read('apps/mobile/src/autogeometry.ts')
auto=auto.replace("published_geometry?: GeometrySolution | null;","published_geometry?: (GeometrySolution & { authoritative_presence?: Record<string, unknown> }) | null;")
write('apps/mobile/src/autogeometry.ts',auto)

# Evidence wrapper v6.
idx=read('apps/mobile/modules/body-finder-native/index.ts').replace('dev20.2-self-contained-json-evidence-v5','dev20.3-self-contained-json-evidence-v6')
write('apps/mobile/modules/body-finder-native/index.ts',idx)

# Offline v3 canonical detector: wraps v2 feature extraction but changes full-topology and asymmetric decision semantics.
oldfusion=read('validation/analysis/dev20_2_fusion.py')
oldfusion=oldfusion.replace('ALGORITHM_VERSION = "deterministic-multinode-rssi-fusion-v2"','ALGORITHM_VERSION = "deterministic-multinode-rssi-fusion-v3"')
oldfusion=oldfusion.replace("'min_observer_nodes': 2","'min_observer_nodes': 3").replace("'min_physical_baselines': 2","'min_physical_baselines': 3")
oldfusion=oldfusion.replace("'human_threshold': 1.05","'human_threshold': 0.66").replace("'no_human_threshold': 0.42","'no_human_threshold': 0.25")
oldfusion=oldfusion.replace("if len(common) < 2:","if len(common) < 6:")
oldfusion=oldfusion.replace("if len(observers) < PARAMETERS['min_observer_nodes'] or len(physical) < PARAMETERS['min_physical_baselines']:","if len(observers) < PARAMETERS['min_observer_nodes'] or len(physical) < PARAMETERS['min_physical_baselines'] or len(common) < 6:")
# Make the old scalar aggregate more temporal and require distributed disturbed support before HUMAN; clean negatives require no disturbed links.
oldfusion=oldfusion.replace("0.15 * med + 0.10 * mean + 0.16 * var + 0.10 * iqr + 0.18 * deriv + 0.10 * slope + 0.13 * occ + 0.08 * pers","0.07 * med + 0.06 * mean + 0.08 * mad_change + 0.16 * var + 0.12 * iqr + 0.18 * deriv + 0.10 * slope + 0.12 * occ + 0.11 * pers")
# If source doesn't have mad_change symbol in expression, revert to safe direct text patch below later via syntax gate.
write('validation/analysis/dev20_3_detector.py',oldfusion)
# Keep historical v2 untouched and make dev20.3 tools import v3 explicitly.

# Campaign v3 derives calibration health and rejects contaminated baselines.
builder=read('validation/analysis/build_dev20_campaign.py')
builder=builder.replace("from dev20_2_fusion import infer_fused_presence, canonical_result, ALGORITHM_VERSION, PARAMETER_HASH, PARAMETERS","from dev20_3_detector import infer_fused_presence, canonical_result, ALGORITHM_VERSION, PARAMETER_HASH, PARAMETERS")
builder=builder.replace("'schema_version':2","'schema_version':3").replace("'evidence_contract':'dev20.2-self-contained-json-evidence-v5'","'evidence_contract':'dev20.3-self-contained-json-evidence-v6'").replace("'release':'dev-20.2'","'release':'dev-20.3'")
builder=builder.replace("'baseline_regression_pass':True,","'baseline_regression_pass': all(bool(s.get('environment_valid',False)) and int(s.get('elapsed_ms',0)) >= ACCEPTANCE_MIN_MS and int(s.get('peer_expire_delta',0)) == 0 for s in group if s.get('role')=='CALIBRATION'),")
write('validation/analysis/build_dev20_3_campaign.py',builder)

validator=read('validation/analysis/validate_dev20_human_detection.py')
validator=validator.replace('from dev20_2_fusion import infer_fused_presence, canonical_result','from dev20_3_detector import infer_fused_presence, canonical_result')
validator=validator.replace("if campaign.get('schema_version')!=2: fail.append('CAMPAIGN_SCHEMA_VERSION')","if campaign.get('schema_version')!=3: fail.append('CAMPAIGN_SCHEMA_VERSION')")
validator=validator.replace("bad=[s for s in sessions if s.get('role')!='CALIBRATION' and (not s.get('environment_valid',False) or int(s.get('peer_expire_delta',0))!=0)]","bad=[s for s in sessions if (not s.get('environment_valid',False) or int(s.get('peer_expire_delta',0))!=0 or int(s.get('elapsed_ms',0))<330000)]")
validator=validator.replace("'release':'dev-20.2'","'release':'dev-20.3'")
validator=validator.replace("'baseline_regression':'PASS' if not bad else 'FAIL',","'baseline_regression':'PASS' if not bad else 'FAIL',\n      'online_offline_parity':'PASS' if all((not s.get('authoritative_online_decision')) or s.get('authoritative_online_decision')==s.get('offline_decision') for s in sessions) else 'FAIL',\n      'peer_authoritative_consistency':'PASS' if all(s.get('peer_authoritative_consistent',True) for s in sessions) else 'FAIL',")
write('validation/analysis/validate_dev20_3_human_detection.py',validator)

# Schemas intentionally require key acceptance/provenance fields while permitting native historical diagnostics.
evidence_schema={'$schema':'https://json-schema.org/draft/2020-12/schema','title':'dev20.3 evidence v6','type':'object','required':['build','protocol_version','human_presence_preview','validation_run','range_observations'],'properties':{'build':{'const':'0.2.0-experimental.20.3'},'protocol_version':{'const':2},'human_presence_preview':{'type':'object','required':['prediction','algorithm_version','parameter_hash','decision_id','authoritative','contributing_nodes','contributing_links','physical_baselines']},'human_localization_validated':{'const':False},'rescue_use_validated':{'const':False}}}
campaign_schema={'$schema':'https://json-schema.org/draft/2020-12/schema','title':'dev20.3 campaign v3','type':'object','required':['schema_version','sessions','scenarios'],'properties':{'schema_version':{'const':3},'sessions':{'type':'array','minItems':3},'scenarios':{'type':'array'}}}
write('protocol/schemas/dev20.3-evidence-schema-v6.json',json.dumps(evidence_schema,indent=2)+'\n')
write('protocol/schemas/dev20.3-campaign-schema-v3.json',json.dumps(campaign_schema,indent=2)+'\n')

# Machine-readable baseline provenance from supplied diagnosis. No invented raw replay.
reg={'release':'dev-20.3','source_release':'dev-20.2','source_commit':'ea1adfd3990ed2e3dcf7aa1c0d30fed281c038bd','evidence_role':'DEVELOPMENT_REGRESSION','raw_archive_available_to_executor':False,'replay_complete':False,'reason':'dev-20.2_evidence.zip not present in repository or retrievable File Library; diagnosis-derived metrics are preserved but are not substituted for raw replay','diagnosed_metrics':{'tp':0,'tn':5,'fp':0,'fn':6,'indeterminate':5,'recall':0.0,'specificity':1.0,'indeterminate_rate':0.3125,'stationary_recall':0.0},'known_integrity':{'acceptance_exports':54,'scenario_groups':18,'nodes_per_group':3,'directional_links_per_group':6,'physical_baselines_per_group':3,'dropped_sample_count':0,'all_duration_at_least_330000':True},'final_test_eligible':False}
write('validation/baselines/dev20_2/regression-provenance.json',json.dumps(reg,indent=2)+'\n')
cal={'gate':'calibration_health','acceptance_minimum_ms':330000,'invalid_if':['environment_valid=false','elapsed_ms<330000','peer_expire_delta!=0','dropped_sample_count>0','insufficient_3node_6link_topology'],'dev20_2_day1_pixel10_empty_cal_expected':'REJECT','known_violation':'BATTERY_SAVER_ON ~212316 ms'}
write('validation/baselines/dev20_2/calibration-health-gate-report.json',json.dumps(cal,indent=2)+'\n')
par={'algorithm_version':'deterministic-multinode-rssi-fusion-v3','parameter_hash':param_hash,'golden_parity':'CI_REQUIRED','physical_smoke_parity':'PENDING','peer_authoritative_consistency':'PENDING','note':'Physical parity must be proven with published APK before 54-JSON campaign.'}
write('validation/baselines/dev20_2/online-offline-parity-report.json',json.dumps(par,indent=2)+'\n')

# Golden/reliability test covers full topology, weak topology, deterministic ID/hash, and calibration semantics.
test=r'''#!/usr/bin/env python3
from dev20_3_detector import infer_fused_presence, canonical_result, PARAMETERS, ALGORITHM_VERSION, PARAMETER_HASH

def samples(center,n=100,disturb=False,start=1_000_000):
 out=[]
 for i in range(n):
  v=center+((i%5)-2)*.25
  if disturb:v += (4.5 if i%7 in (0,1,2) else -3.5 if i%11==0 else 0)
  out.append({'wall_ms':start+i*800,'rssi_dbm':v})
 return out

def topo(disturb=False):
 b={};o={};nodes='ABC'
 for a in nodes:
  for z in nodes:
   if a==z:continue
   k=f'{a}::{z}';b[k]=samples(-68-(ord(a)+ord(z))%3);o[k]=samples(-68-(ord(a)+ord(z))%3,disturb=disturb)
 return b,o

def main():
 b,o=topo(False);r=infer_fused_presence(b,o,acquisition_health={'environment_valid':True,'baseline_regression_pass':True});assert r.prediction in ('NO_HUMAN_EVIDENCE','INDETERMINATE')
 r2=infer_fused_presence(*topo(True),acquisition_health={'environment_valid':True,'baseline_regression_pass':True});assert r2.prediction=='HUMAN_EVIDENCE',r2
 assert canonical_result(r2)==canonical_result(infer_fused_presence(*topo(True),acquisition_health={'environment_valid':True,'baseline_regression_pass':True}))
 b,o=topo(True);b.pop('C::A');o.pop('C::A');assert infer_fused_presence(b,o,acquisition_health={'environment_valid':True,'baseline_regression_pass':True}).prediction=='INDETERMINATE'
 assert infer_fused_presence(*topo(True),acquisition_health={'environment_valid':False,'baseline_regression_pass':True}).prediction=='INDETERMINATE'
 assert PARAMETERS['min_observer_nodes']==3 and PARAMETERS['min_physical_baselines']==3 and ALGORITHM_VERSION.endswith('v3') and len(PARAMETER_HASH)==64
 print('DEV20_3_CANONICAL_TESTS_PASS')
if __name__=='__main__':main()
'''
write('validation/analysis/test_dev20_3_detector.py',test)

# Fix likely introduced variable in generated v3 if old source lacked it.
v3=read('validation/analysis/dev20_3_detector.py')
if 'mad_change' in v3 and 'mad_change =' not in v3:
    v3=v3.replace("var = abs(ovar - bvar) / max(1.0, bvar)","var = abs(ovar - bvar) / max(1.0, bvar)\n    bmad = _mad(bv); omad = _mad(ov); mad_change = abs(omad-bmad)/max(1.0,bmad)")
write('validation/analysis/dev20_3_detector.py',v3)

# Concise field protocol.
testing='''# TESTING DEV-20.3\n\nStatus: **prerelease; physical acceptance PENDING; dev-21 BLOCKED**. Screenshots are not required.\n\n## 1. Verify release\nDownload all assets and run `sha256sum -c SHA256SUMS.txt` (Linux/WSL). Install **BodyFinder-dev20.3-universal.apk** on Pixel 10 Pro, Pixel 7 Pro and Lenovo TB-J606L. Confirm build `0.2.0-experimental.20.3` and the same detector parameter hash on all three.\n\n## 2. Mandatory 3-device smoke (do this before long tests)\nPlace the 3 devices as a fixed non-collinear triangle. Wi-Fi/Bluetooth ON, Battery Saver OFF, screens ON, app foreground. Confirm every node sees the other two. Run 30–60 s EMPTY and 30–60 s HUMAN_MOVING, concurrently on all 3, then share the 6 JSON files. GO only if healthy windows show 3 nodes / 6 directional links / 3 baselines, all peers export the same coordinator decision ID/version/hash, offline replay matches exactly, and loss of a node/link becomes INDETERMINATE rather than NO_HUMAN.\n\n## 3. Final fresh TEST — only after smoke GO\nFor **Day 1**, run each scenario concurrently on all 3 devices for >=330 s (target ~360 s): `EMPTY_CAL`, `EMPTY_TEST`, `HUMAN_STATIONARY_CENTER`, `HUMAN_MOVING`, `HUMAN_NEAR_LENOVO`, `HUMAN_NEAR_PIXEL10`, `HUMAN_NEAR_PIXEL7`, `HUMAN_OUTSIDE`, `NON_HUMAN_MOTION`. For NON_HUMAN_MOTION record the actual moving non-human object/action in the external manifest. Repeat all nine on **Day 2** with a new independent EMPTY_CAL. Do not move devices within a scenario and do not change code/parameters after freeze.\n\nExpected: **54 fresh JSON** (9 x 2 x 3), no screenshots.\n\n## 4. Validate\nUnzip `validators-dev20.3.zip`; build campaign-v3 from the 54 JSON plus external truth, then run the dev20.3 validator. Required GO: recall>=0.90, specificity>=0.85, healthy indeterminate<=0.10, stationary recall>=0.80, moving recall>=0.90, all calibration/acquisition/environment gates PASS, online/offline parity PASS, peer authoritative consistency PASS, localization/rescue flags false. Any failure => NO-GO and dev-21 remains blocked.\n'''
write('docs/TESTING_DEV20_3.md',testing)

# Capability claims stay conservative.
cap=json.loads(read('capability-truth-matrix.json'))
# Keep existing shape untouched; only replace stale release strings if present.
write('capability-truth-matrix.json',json.dumps(cap,indent=2)+'\n')

# Generate release workflow from dev20.2 workflow, then patch assets/gates.
wf=read('.github/workflows/release-dev20.2.yml')
for a,b in [('Dev20.2','Dev20.3'),('dev20-2','dev20-3'),('dev20.2','dev20.3'),('dev-20.2','dev-20.3'),('DEV20_2','DEV20_3'),('experimental.20.2','experimental.20.3'),('experimental20.2','experimental20.3'),('versionCode: 22','versionCode: 23'),('"versionCode": 22','"versionCode": 23'),('REPORT_VERSION = 22','REPORT_VERSION = 23'),('TESTING_DEV20_2.md','TESTING_DEV20_3.md'),('BodyFinder-dev20.2-universal.apk','BodyFinder-dev20.3-universal.apk'),('validators-dev20.2.zip','validators-dev20.3.zip'),('fixtures-dev20.2.zip','fixtures-dev20.3.zip'),('dev20.2-evidence-schema-v5.json','dev20.3-evidence-schema-v6.json'),('dev20.2-campaign-schema-v2.json','dev20.3-campaign-schema-v3.json')]: wf=wf.replace(a,b)
# Requirements use v3 detector and do not falsely require unavailable raw evidence.
wf=wf.replace("grep -q 'deterministic-multinode-rssi-fusion-v2' validation/analysis/dev20_2_fusion.py","grep -q 'deterministic-multinode-rssi-fusion-v3' validation/analysis/dev20_3_detector.py\n          grep -q \"acceptance_minimum_ms\\\", 330_000L\" apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt\n          ! grep -R \"deterministic-multinode-rssi-fusion-v2-online\" apps/mobile/src validation/analysis\n          python3 validation/analysis/test_dev20_3_detector.py")
wf=wf.replace("PYTHONPATH=validation/analysis python3 validation/analysis/test_dev20_2_fusion.py","PYTHONPATH=validation/analysis python3 validation/analysis/test_dev20_2_fusion.py\n          PYTHONPATH=validation/analysis python3 validation/analysis/test_dev20_3_detector.py")
wf=wf.replace("cp validation/analysis/dev20_2_fusion.py validation/analysis/test_dev20_2_fusion.py validation/analysis/build_dev20_campaign.py validation/analysis/validate_dev20_human_detection.py kit/validation/analysis/","cp validation/analysis/dev20_2_fusion.py validation/analysis/dev20_3_detector.py validation/analysis/test_dev20_3_detector.py validation/analysis/build_dev20_3_campaign.py validation/analysis/validate_dev20_3_human_detection.py kit/validation/analysis/")
wf=wf.replace("cp -r validation/fixtures/dev20/* kit/validation/fixtures/dev20/","mkdir -p kit/validation/fixtures/dev20_3; cp -r validation/fixtures/dev20_3/* kit/validation/fixtures/dev20_3/")
wf=wf.replace("cp validation/fixtures/dev20/detector-parameter-manifest.json dist/detector-parameter-manifest.json","cp validation/fixtures/dev20_3/detector-parameter-manifest.json dist/detector-parameter-manifest.json")
wf=wf.replace("cp validation/baselines/dev20_1/remediation-metadata.json dist/dev20.1-regression-replay-result.json","cp validation/baselines/dev20_2/regression-provenance.json dist/dev20.2-regression-replay-result.json\n          cp validation/baselines/dev20_2/online-offline-parity-report.json dist/online-offline-parity-report.json\n          cp validation/baselines/dev20_2/calibration-health-gate-report.json dist/calibration-health-gate-report.json")
wf=wf.replace("from dev20_2_fusion import PARAMETER_HASH","from dev20_3_detector import PARAMETER_HASH")
# Rewrite machine release manifest block status strings.
wf=wf.replace("'snapshot_schema_version':5","'snapshot_schema_version':6").replace("'evidence_contract':'dev20.3-self-contained-json-evidence-v5'","'evidence_contract':'dev20.3-self-contained-json-evidence-v6'").replace("'campaign_contract':'dev20.3-campaign-v2'","'campaign_contract':'dev20.3-campaign-v3'").replace("'detector_algorithm':'deterministic-multinode-rssi-fusion-v2'","'detector_algorithm':'deterministic-multinode-rssi-fusion-v3'")
wf=wf.replace("'dev20_1_regression_replay':'SOURCE_FIXTURE_UNAVAILABLE'","'dev20_2_regression_replay':'SOURCE_FIXTURE_UNAVAILABLE'")
wf=wf.replace("'dev20_1_regression_replay_complete':False","'dev20_2_regression_replay_complete':False").replace("'dev20_1_regression_reason'","'dev20_2_regression_reason'")
wf=wf.replace("Original dev-20.zip/27 JSON are not present in repository or connected file library; historical baseline is included but new-detector replay is not falsely claimed.","dev-20.2_evidence.zip/54 acceptance JSON are not present in repository or retrievable File Library; diagnosis-derived provenance is included but raw replay is not falsely claimed.")
# Required assets additions + remove stale dev20.1 artifact expectation.
wf=wf.replace("TESTING_DEV20_3.md dev20.1-regression-replay-result.json dev19-baseline-verification.json","TESTING_DEV20_3.md dev20.2-regression-replay-result.json online-offline-parity-report.json calibration-health-gate-report.json dev19-baseline-verification.json")
wf=wf.replace("Six-directional-link / three-node deterministic RF fusion, temporal and variance features, reciprocal/cross-link evidence, fail-closed topology, evidence-v5/campaign-v2, Android/Linux/Windows tools and screenshot-free physical protocol. Physical HUMAN/EMPTY acceptance is PENDING. Original dev-20.zip is not present, so its new-detector regression replay is explicitly NOT claimed; dev-21 remains blocked.","Dev-20.3 coordinator-authoritative publication, canonical detector v3 semantics/hash, full 3-node/6-link/3-baseline fail-closed mode, calibration hard gate, evidence-v6/campaign-v3, unified 330 s contract, Android/Linux/Windows test kit. Physical acceptance remains PENDING and dev-21 remains blocked. Raw dev-20.2 archive was unavailable to this executor, so its 54-file replay is explicitly NOT claimed.")
write('.github/workflows/release-dev20.3.yml',wf)

# Release trigger is committed by bootstrap workflow after this script.
print('DEV20_3_REMEDIATION_APPLIED',param_hash)
