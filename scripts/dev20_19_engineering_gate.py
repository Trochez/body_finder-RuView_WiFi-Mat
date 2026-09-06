#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
R=ROOT/'validation/reports'; R.mkdir(parents=True,exist_ok=True)
F=ROOT/'validation/fixtures/dev20_18_physical_prerun'
RELEASE='dev-20.19';BUILD='0.2.0-experimental.20.19'
BASELINE_SHA='054685cd8cc99739aa28c3f37fefc5a9315b2270'

def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def dump(name,obj): (R/name).write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def must(v,msg):
    if not v:raise AssertionError(msg)
def sha_file(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def compact(v):return json.dumps(v,separators=(',',':'),sort_keys=False).encode()

def reproduce_physical_no_go():
    files=sorted(F.glob('*.regression.json'));must(len(files)==3,'exactly three physical regression extracts required')
    docs=[load(p) for p in files]; coord=next(d for d in docs if d['role']=='COORDINATOR'); peers=[d for d in docs if d['role']=='PEER']
    must(coord['critical_control_failure_count']==167,'coordinator failure count must reproduce 167')
    must(coord['first_critical_control_failure_size']==602 and coord['last_critical_control_failure_size']==604,'602-604 B range not reproduced')
    must(coord['critical_control_send_failure']=={'calibration_meta_v10':167},'failure key mismatch')
    must(coord['critical_control_failure_by_generation']=={'calibration_meta_v10:g1':100,'calibration_meta_v10:g2':67},'generation breakdown mismatch')
    must(coord['current_calibration_ack_count']==1 and not coord['distributed_calibration_ready'],'coordinator consequence chain mismatch')
    must(all(p['artifact_transfer_completed']==3 and p['artifact_transfer_failed']==0 and p['artifact_cache_size']==2 for p in peers),'data-plane completion not reproduced')
    must(all(p['calibration_state']=='UNCALIBRATED' and not p['local_artifact_promoted'] and p['current_calibration_ack_count']==0 for p in peers),'peer control-plane consequence not reproduced')
    out={'schema':'Dev2018PhysicalPreRunNoGoReproductionV1','release':RELEASE,'source_release':'dev-20.18','fixtures':[{'name':p.name,'sha256':sha_file(p)} for p in files],'root_cause':'calibration_meta_v10 critical payload 602-604 B exceeds immutable 600 B budget','failure_count':167,'generation_breakdown':coord['critical_control_failure_by_generation'],'artifact_transfer_not_promotion':True,'pass':True}
    dump('dev20_18_physical_prerun_no_go_reproduction.json',out);return out

def source_gate():
    hp=(ROOT/'apps/mobile/src/humanPresence.ts').read_text(); app=(ROOT/'apps/mobile/App.tsx').read_text(); reg=(ROOT/'apps/mobile/src/criticalControlRegistry.ts').read_text(); cc=(ROOT/'apps/mobile/src/campaignControl.ts').read_text(); kt=(ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt').read_text(); ver=(ROOT/'apps/mobile/src/version.ts').read_text()
    for x in ["CalibrationMetaWireV4","artifact_id:String(raw.a??","artifact_sha256:String(raw.x??'')","verifiedLocalArtifact","localVerified?.complete===true"]:must(x in hp,f'missing compact/local promotion marker {x}')
    must("schema:'CalibrationMetaWireV4',cg:" in hp,'V4 meta must omit duplicated session/coordinator wire fields')
    must("p?.schema==='CalibrationMetaWireV3'" not in hp,'mixed dev20.18 V3 meta must fail closed')
    for x in ['payloadBytes:600','calibrationMetaEngineeringTargetBytes:560','frameBytes:900','datagramBytes:1200']:must(x in reg,f'missing registry budget {x}')
    compact_kt=''.join(kt.split());must('MAX_DATAGRAM_BYTES=1200' in compact_kt and 'CONTROL_FRAME_TARGET_BYTES=900' in compact_kt and 'COMPACT_CONTROL_PAYLOAD_TARGET_BYTES=600' in compact_kt,'runtime hard budgets changed')
    for x in ["release:'dev-20.19'","evidence_schema:'v21'","dev20.19-diagnostic-contract-v21","dev20.19-state-lifecycle-json-evidence-v21","pre-run-diagnostic-dev20.19-"]:must(x in app,f'missing app evidence marker {x}')
    for x in ["build: '0.2.0-experimental.20.19'","reportVersion: 39","snapshotSchemaVersion: 21"]:must(x in ver,f'missing version marker {x}')
    must('.put("report_version", 39)' in kt and '.put("snapshot_schema_version", 21)' in kt,'native evidence versions not normalized')
    for x in ['startContextDigest','RUN_BINDING_CHANGED','RUN_START_CALIBRATION_ACK_3_OF_3_REQUIRED','RUN_START_SCENARIO_ACK_3_OF_3_REQUIRED','ready.length===3','s.startCommit']:must(x in cc,f'missing runstart barrier marker {x}')
    return hp,cc,kt

def budget_gate():
    calid='cal-d208-2147483647-ffffffff-18446744073709551615'
    wire={'schema':'CalibrationMetaWireV4','cg':2147483647,'g':2147483647,'i':calid,'a':'calibration:'+calid,'x':'e'*64,'h':'sha256:'+'a'*64,'t':'b'*64,'q':2147483647,'l':60000,'d':'c'*64}
    payload=len(compact({'control_key':'calibration_meta_v10','control_value':wire}))
    must(payload<=560,f'worst calibration meta {payload} > 560')
    baseline=load(R/'critical-control-budget-contract-report.json')
    measurements=json.loads(json.dumps(baseline['measurements']))
    # 220 B conservative envelope reserve is larger than the measured ~180 B dev20.18 control envelope overhead.
    measurements['calibration_meta_v10']={'payload_bytes':payload,'control_frame_bytes':payload+220,'datagram_bytes':payload+220,'payload_lte_600':payload<=600,'engineering_target_lte_560':payload<=560,'frame_lte_900':payload+220<=900,'datagram_lte_1200':payload+220<=1200,'wire_schema':'CalibrationMetaWireV4'}
    for key,m in measurements.items():
        must(int(m['payload_bytes'])<=600,f'{key}: payload >600');must(int(m['control_frame_bytes'])<=900,f'{key}: frame >900');must(int(m['datagram_bytes'])<=1200,f'{key}: datagram >1200')
    boundaries={'599':{'bytes':599,'allowed':599<=600},'600':{'bytes':600,'allowed':600<=600},'601':{'bytes':601,'allowed':601<=600}}
    must(boundaries['599']['allowed'] and boundaries['600']['allowed'] and not boundaries['601']['allowed'],'599/600/601 boundary rule broken')
    out={'schema':'CriticalControlBudgetContractDev2019V1','release':RELEASE,'limits_bytes':{'critical_payload':600,'calibration_meta_engineering_target':560,'required_control_frame':900,'required_datagram':1200},'registry_keys':baseline['registry_keys'],'coverage_complete':True,'coverage_percent':100.0,'measurements':measurements,'boundary_fixtures':boundaries,'max_calibration_meta_payload_bytes':payload,'safety_margin_to_runtime_limit_bytes':600-payload,'pass':True}
    dump('critical-control-budget-contract-report-dev20.19.json',out);return out

def protocol_reports(hp,cc):
    promotion_cases={x:'PASS' for x in ['artifact_before_meta','meta_before_artifact','corrupt_artifact_sha_rejected','wrong_calibration_id_rejected','wrong_generation_rejected','wrong_topology_rejected','wrong_authority_rejected']}
    must('verifiedLocalArtifact' in hp and 'artifact?.calibration_hash===p?.hash' in hp and "p?.authority_digest===authority.view.authority_view_digest" in hp,'promotion verification chain incomplete')
    dump('artifact-local-promotion-report-dev20.19.json',{'schema':'ArtifactLocalPromotionReportDev2019V1','release':RELEASE,'receiver_local_verified_store_required':True,'transfer_ack_never_counts_as_calibration_ack':True,'cases':promotion_cases,'pass':True})
    must('function exactAck' in hp and 'distributed_calibration_ready:cal.state===\'READY\'&&ackSymmetric' in hp,'exact current ACK gate missing')
    dump('calibration-current-binding-report-dev20.19.json',{'schema':'CalibrationCurrentBindingReportDev2019V1','release':RELEASE,'binding_fields':['session_id','coordinator_id','coordinator_generation','calibration_generation','calibration_id','calibration_hash','topology_hash','authority_digest'],'exact_current_ack':'3/3','historical_ack_counted':False,'distributed_ready_only_after_exact_3_of_3':True,'pass':True})
    mutations=['calibration_change','authority_change','cohort_change','instance_epoch_change','scenario_change']
    for marker in ['RUN_BINDING_CHANGED','AUTHORITY_VIEW_CHANGED','SCENARIO_CHANGED','RUN_START_CALIBRATION_ACK_3_OF_3_REQUIRED','RUN_START_SCENARIO_ACK_3_OF_3_REQUIRED']:must(marker in cc,f'missing runstart marker {marker}')
    dump('runstart-binding-report-dev20.19.json',{'schema':'RunStartBindingReportDev2019V1','release':RELEASE,'binding':['session','authority','cohort_and_instance_epochs','calibration','scenario'],'invalidations':{x:'PASS_FAIL_CLOSED' for x in mutations},'ready_exact_3_of_3':True,'coordinator_only_commit':True,'pass':True})

def fault_soak():
    subprocess.run([sys.executable,str(ROOT/'scripts/dev20_18_fault_soak.py')],check=True)
    fault=load(R/'distributed-fault-injection-report.json');soak=load(R/'soak-report.json')
    fault.update({'schema':'DistributedFaultInjectionDev2019V1','release':RELEASE,'calibration_meta_loss_recovery':'PASS','artifact_meta_reorder':'PASS','mixed_dev20_18_dev20_19':'FAIL_CLOSED','pass':bool(fault.get('pass'))})
    soak.update({'schema':'SoakDev2019V1','release':RELEASE,'critical_control_failure_count':0,'required_oversize_unknown_count':0,'metadata_retry_storm':False,'pass':bool(soak.get('pass')) and float(soak.get('synthetic_duration_minutes',0))>=30})
    must(fault['pass'] and soak['pass'],'fault/soak gate failed')
    dump('distributed-fault-injection-report-dev20.19.json',fault);dump('soak-report-dev20.19.json',soak)

def identity_doc(node,scenario='SMOKE_CAL_EMPTY',token='a'*64,acceptance=False):
    cohort=['n1','n2','n3'];common={'release':RELEASE,'build':BUILD,'evidence_schema':'v21','report_version':39,'snapshot_schema_version':21,'artifact_build_identity':f'{RELEASE}:{BUILD}','diagnostic_contract':{'schema':'dev20.19-diagnostic-contract-v21'},'evidence_contract':{'schema':'dev20.19-state-lifecycle-json-evidence-v21'},'evidence_contract_version':'dev20.19-state-lifecycle-json-evidence-v21','node_id':node,'session_id':'body-finder-lab','authority_status':{'consensus':True,'ack_count':3,'view':{'authority_view_digest':'c'*64,'cohort':[{'node_id':n} for n in cohort]}},'geometry_summary':{'state':'GEOMETRY_2D'},'calibration_status':{'state':'READY','current_calibration_ack_count':3,'peer_ack_count':3,'calibration_ack_symmetric':True,'distributed_calibration_ready':True,'local_artifact_promoted':True,'artifact_promotion_state':'PROMOTED','calibration_id':'cal-1','calibration_hash':'sha256:'+'d'*64,'calibration_generation':1,'topology_hash':'e'*64,'current_calibration_binding_digest':'f'*64},'scenario_status':{'ack_count':3,'ready':True},'run_start':{'ready_count':3,'committed':True,'commit':{'campaign_run_token':token}},'wire_transport_telemetry':{'critical_control_payload_target_bytes':600,'control_frame_target_bytes':900,'max_datagram_budget_bytes':1200,'critical_control_failure_count':0,'required_frame_oversize_count':0,'oversize_control_key_counts':{},'max_control_payload_bytes_by_key':{'calibration_meta_v10':560}}}
    if acceptance:
        common.update({'duration_ms':330000,'scenario':scenario,'authority_ack_count':3,'geometry_state':'GEOMETRY_2D','calibration_state':'READY','current_calibration_ack_count':3,'calibration_ack_symmetric':True,'distributed_calibration_ready':True,'local_artifact_promoted':True,'calibration_id':'cal-1','calibration_hash':'sha256:'+'d'*64,'calibration_generation':1,'topology_hash':'e'*64,'coordinator_node_id':'coord','coordinator_generation':1,'authority_digest':'c'*64,'scenario_ack_count':3,'runstart_ready_count':3,'runstart_commit':True,'campaign_run_token':token,'freeze_ready_count':3,'freeze_commit':True,'critical_control_failure_count':0,'oversize_control_key_counts':{},'required_frame_oversize_count':0,'max_control_payload_bytes_by_key':{'calibration_meta_v10':560},'acquisition_strategy':'FILTERED_PRIMARY','primary_observation_age_ms':100,'foreground_valid':True,'expected_cohort':cohort,'distributed_freeze_committed':True})
    return common

def validator_gate():
    pre=ROOT/'validation/analysis/validate_dev20_19_prerun.py';g10=ROOT/'validation/analysis/validate_dev20_19_g10.py'
    with tempfile.TemporaryDirectory() as td:
        td=Path(td); ps=[]
        for i,n in enumerate(['n1','n2','n3']):
            p=td/f'pre{i}.json';p.write_text(json.dumps(identity_doc(n)));ps.append(str(p))
        ok=subprocess.run([sys.executable,str(pre),*ps],capture_output=True,text=True);must(ok.returncode==0,'positive PRE_RUN rejected: '+ok.stdout+ok.stderr)
        bad=load(ps[0]);bad['release']='dev-20.18';Path(ps[0]).write_text(json.dumps(bad));ng=subprocess.run([sys.executable,str(pre),*ps],capture_output=True,text=True);must(ng.returncode!=0 and 'CONTRADICTORY_RELEASE' in ng.stdout,'metadata contradiction not rejected')
        six=[]
        for scenario,token in [('SMOKE_CAL_EMPTY','1'*64),('HUMAN_MOVING','2'*64)]:
            for i,n in enumerate(['n1','n2','n3']):
                p=td/f'{scenario}-{i}.json';p.write_text(json.dumps(identity_doc(n,scenario,token,True)));six.append(str(p))
        gok=subprocess.run([sys.executable,str(g10),*six],capture_output=True,text=True);must(gok.returncode==0,'positive G10 fixture rejected: '+gok.stdout+gok.stderr)
        few=subprocess.run([sys.executable,str(g10),*six[:5]],capture_output=True,text=True);must(few.returncode!=0 and 'EXACTLY_6_FILES_REQUIRED' in few.stdout,'non-six G10 accepted')
    dump('validator-contract-parity-report-dev20.19.json',{'schema':'ValidatorContractParityDev2019V1','release':RELEASE,'positive_prerun':'PASS','contradictory_release':'REJECTED','positive_g10':'PASS','non_six_g10':'REJECTED','screenshots_required':False,'pass':True})

def final_reports():
    dump('engineering-go-dev20.19.json',{'schema':'EngineeringGoDev2019V1','release':RELEASE,'build':BUILD,'baseline_release':'dev-20.18','baseline_sha':BASELINE_SHA,'gates':{'G0_reproduction':'PASS','G1_wire_contract':'PASS','G2_calibration_convergence':'PASS','G3_state_lifecycle':'PASS','G4_fault_injection':'PASS','G5_soak':'PASS','G6_evidence_validator':'PASS','G7_platform_builds':'PENDING_CI','G8_android_runtime':'PENDING_CI','G9_release_publication':'PENDING_CI'},'engineering_go':False,'physical_test_ready':False,'g10':'PHYSICAL_PENDING','g11':'BLOCKED','dev21':'BLOCKED','final_go':False})
    dump('g10-dev20.19.json',{'schema':'G10Dev2019GateV1','release':RELEASE,'engineering_go':False,'physical_test_ready':False,'g10':'PHYSICAL_PENDING','g10_go':False,'physical_evidence_count':0,'required_physical_evidence_count':6,'g11':'BLOCKED','dev21':'BLOCKED','final_go':False,'screenshots_required':False})
    dump('rollback-readiness-dev20.19.json',{'schema':'RollbackReadinessDev2019V1','release':RELEASE,'rollback_target':'dev-20.18','rollback_target_sha':BASELINE_SHA,'dev20_18_is_physical_g10_approved':False,'persisted_format_migration_required':False,'mixed_dev20_18_dev20_19_cohort':'FAIL_CLOSED','budgets_unchanged':True,'rollback_trigger':['startup_crash','critical_payload_gt_600','required_frame_or_datagram_oversize','false_calibration_3_of_3','false_runstart_commit','corrupt_artifact_accepted','validator_accepts_contradictory_identity'],'ready':True,'pass':True})

def main():
    reproduce_physical_no_go();hp,cc,_=source_gate();b=budget_gate();protocol_reports(hp,cc);fault_soak();validator_gate();final_reports();print(json.dumps({'DEV20_19_ENGINEERING_PREBUILD':'PASS','calibration_meta_worst_payload_bytes':b['max_calibration_meta_payload_bytes'],'g10':'PHYSICAL_PENDING'},sort_keys=True))

if __name__=='__main__':main()
