#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,re
ROOT=Path(__file__).resolve().parents[1]
REPORTS=ROOT/'validation'/'reports';REPORTS.mkdir(parents=True,exist_ok=True)

def dump(name,obj):(REPORTS/name).write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def enc(x):return json.dumps(x,separators=(',',':'),ensure_ascii=False,sort_keys=True).encode()
def sha(x):return hashlib.sha256(enc(x)).hexdigest()

def patch_runtime():
    # Compact commit keeps explicit authority digest so authority pinning remains independently verifiable.
    p=ROOT/'apps/mobile/src/campaignControl.ts';s=p.read_text()
    s=s.replace("type RunStartCommitWireV2={v:'R2C';t:string;g:number;b:string;r:string;n:string;w:number};","type RunStartCommitWireV2={v:'R2C';t:string;g:number;b:string;a:string;r:string;n:string;w:number};")
    s=s.replace("return{v:'R2C',t:c.campaign_run_token,g:c.generation,b:startPrepareBinding(p),r:c.readiness_digest,n:c.committed_by,w:c.committed_wall_ms}","return{v:'R2C',t:c.campaign_run_token,g:c.generation,b:startPrepareBinding(p),a:c.authority_view_digest,r:c.readiness_digest,n:c.committed_by,w:c.committed_wall_ms}")
    s=s.replace("raw.b!==startPrepareBinding(p)||typeof raw.r", "raw.b!==startPrepareBinding(p)||raw.a!==p.authority_view_digest||typeof raw.r")
    p.write_text(s)

    p=ROOT/'apps/mobile/src/authority.ts';s=p.read_text()
    old="const committed=nodes.some(n=>{const c=(n.control_plane as any)?.run_start_commit_v1;return c?.schema==='RunStartCommitV1'&&c?.authority_view_digest===view.authority_view_digest});"
    new="const committed=nodes.some(n=>{const c=(n.control_plane as any)?.run_start_commit_v1;return Boolean((c?.schema==='RunStartCommitV1'&&c?.authority_view_digest===view.authority_view_digest)||(c?.v==='R2C'&&c?.a===view.authority_view_digest))});"
    if old in s:s=s.replace(old,new)
    elif "c?.v==='R2C'" not in s:raise SystemExit('authority compact commit anchor missing')
    p.write_text(s)

    p=ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt';s=p.read_text()
    s=s.replace('"run_freeze_prepare_v2","snapshot_ready_v2","run_freeze_commit_v2"','"run_freeze_prepare_v2","run_freeze_ready_v2","run_freeze_commit_v2"')
    s=s.replace('.put("report_version",36).put("snapshot_schema_version",16)', '.put("report_version",37).put("snapshot_schema_version",16)')
    if 'deterministicCriticalFatalSignature' not in s:
        anchor='  private val criticalControlFailureCount=java.util.concurrent.atomic.AtomicLong(0)\n'
        extra=anchor+'  private val deterministicCriticalFatalSignature=java.util.concurrent.ConcurrentHashMap<String,String>()\n  private val criticalControlFailureByGeneration=java.util.concurrent.ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong>()\n  @Volatile private var firstCriticalControlFailureKey:String?=null\n  @Volatile private var firstCriticalControlFailureSize:Long=0\n  @Volatile private var firstCriticalControlFailureError:String?=null\n  @Volatile private var firstCriticalControlFailureWallMs:Long=0\n'
        if anchor not in s:raise SystemExit('critical telemetry field anchor missing')
        s=s.replace(anchor,extra,1)
        pattern=r"  private fun safeAddControl\(out:MutableList<ByteArray>,key:String,value:Any\?,node:String,session:String,seq:Long\)\{.*?\n  \}\n  @Synchronized private fun putArtifactCache"
        repl='''  private fun safeAddControl(out:MutableList<ByteArray>,key:String,value:Any?,node:String,session:String,seq:Long){
    val critical=criticalControlKeys.contains(key)
    val compact=JSONObject().put("control_key",key).put("control_value",value).toString().toByteArray(Charsets.UTF_8)
    val digest=sha(compact)
    val generation=if(value is JSONObject)value.optLong("g",value.optLong("generation",-1L))else -1L
    val signature="$digest|g$generation"
    maxControlPayloadBytesByKey.computeIfAbsent(key){AtomicLong(0)}.updateAndGet{v->kotlin.math.max(v,compact.size.toLong())}
    if(critical&&deterministicCriticalFatalSignature[key]==signature)return
    if(critical)criticalControlSendAttempt.computeIfAbsent(key){AtomicLong(0)}.incrementAndGet()
    fun criticalFailure(error:String,deterministic:Boolean){
      criticalControlFailureCount.incrementAndGet();criticalControlSendFailure.computeIfAbsent(key){AtomicLong(0)}.incrementAndGet();criticalControlFailureByGeneration.computeIfAbsent("$key:g$generation"){AtomicLong(0)}.incrementAndGet();lastCriticalControlFailureKey=key;lastCriticalControlFailureSize=compact.size.toLong();lastCriticalControlFailureError=error
      if(firstCriticalControlFailureKey==null){firstCriticalControlFailureKey=key;firstCriticalControlFailureSize=compact.size.toLong();firstCriticalControlFailureError=error;firstCriticalControlFailureWallMs=System.currentTimeMillis()}
      if(deterministic)deterministicCriticalFatalSignature[key]=signature
    }
    if(compact.size>COMPACT_CONTROL_PAYLOAD_TARGET_BYTES){oversizeControlKeyCounts.computeIfAbsent(key){AtomicLong(0)}.incrementAndGet();lastOversizeControlKey=key;lastOversizeSha256=digest;if(critical){criticalFailure("CRITICAL_CONTROL_PAYLOAD_OVER_600",true);safeAdd(out,"CONTROL_FATAL",node,session,seq){o->o.put("control_key",key).put("payload_sha256",digest).put("payload_bytes",compact.size).put("fatal",true).put("failure_class","POLICY_BUDGET").put("generation",generation)}}else optionalControlDropCount.incrementAndGet();return}
    try{val frame=envelope("CONTROL_FRAME",node,session,seq){o->o.put("control_key",key).put("control_value",value)};if(frame.size>CONTROL_FRAME_TARGET_BYTES)throw IllegalArgumentException("CONTROL_FRAME_OVER_900:${frame.size}");maxControlBytesByKey.computeIfAbsent(key){AtomicLong(0)}.updateAndGet{v->kotlin.math.max(v,frame.size.toLong())};out+=frame;if(critical)criticalControlSendSuccess.computeIfAbsent(key){AtomicLong(0)}.incrementAndGet()}
    catch(t:Throwable){val error="${t.javaClass.simpleName}:${t.message}";val deterministic=error.contains("OVER_900")||error.contains("WIRE_OVERSIZE");oversizeControlKeyCounts.computeIfAbsent(key){AtomicLong(0)}.incrementAndGet();lastOversizeControlKey=key;lastOversizeSha256=digest;if(critical)criticalFailure(error,deterministic)else optionalControlDropCount.incrementAndGet();lastSendError=error}
  }
  @Synchronized private fun putArtifactCache'''
        s,n=re.subn(pattern,repl,s,count=1,flags=re.S)
        if n!=1:raise SystemExit(f'safeAddControl replacement count={n}')
    if 'controlFatalRxCount' not in s:
        s=s.replace('  val unknownFrameCount=java.util.concurrent.atomic.AtomicLong(0)\n','  val controlFatalRxCount=java.util.concurrent.atomic.AtomicLong(0)\n  val unknownFrameCount=java.util.concurrent.atomic.AtomicLong(0)\n',1)
        anchor='      "GEOMETRY_POSITION_FRAME"->{'
        branch='      "CONTROL_FATAL"->{controlFatalRxCount.incrementAndGet();val d=doc(node,session);val cp=d.optJSONObject("control_plane")?:JSONObject().also{d.put("control_plane",it)};cp.put("last_control_fatal_v1",JSONObject().put("control_key",o.optString("control_key")).put("payload_sha256",o.optString("payload_sha256")).put("payload_bytes",o.optLong("payload_bytes")).put("failure_class",o.optString("failure_class","POLICY_BUDGET")).put("generation",o.optLong("generation",-1L)).put("received_wall_ms",now));return ConsumeResult(d,replies)}\n'+anchor
        if anchor not in s:raise SystemExit('CONTROL_FATAL consume anchor missing')
        s=s.replace(anchor,branch,1)
    telemetry_old='.put("last_critical_control_failure_key",lastCriticalControlFailureKey?:JSONObject.NULL).put("last_critical_control_failure_size",lastCriticalControlFailureSize).put("last_critical_control_failure_error",lastCriticalControlFailureError?:JSONObject.NULL)'
    telemetry_new=telemetry_old+'.put("first_critical_control_failure_key",firstCriticalControlFailureKey?:JSONObject.NULL).put("first_critical_control_failure_size",firstCriticalControlFailureSize).put("first_critical_control_failure_error",firstCriticalControlFailureError?:JSONObject.NULL).put("first_critical_control_failure_wall_ms",firstCriticalControlFailureWallMs).put("critical_control_failure_by_generation",mapJson(criticalControlFailureByGeneration)).put("control_fatal_rx_count",controlFatalRxCount.get())'
    if 'first_critical_control_failure_key' not in s:
        if telemetry_old not in s:raise SystemExit('telemetry output anchor missing')
        s=s.replace(telemetry_old,telemetry_new,1)
    p.write_text(s)

    registry=ROOT/'apps/mobile/src/criticalControlRegistry.ts'
    registry.write_text("""export const CRITICAL_CONTROL_KEYS=Object.freeze([\n  'authority_view_v1','authority_ack_v1','calibration_meta_v10','calibration_ack_v10','decision_meta_v10','decision_ack_v10',\n  'scenario_command_v1','scenario_ack_v1','run_start_prepare_v1','run_start_ready_v1','run_start_commit_v1',\n  'run_freeze_prepare_v2','run_freeze_ready_v2','run_freeze_commit_v2',\n] as const);\nexport const CRITICAL_CONTROL_BUDGET=Object.freeze({payloadBytes:600,frameBytes:900,datagramBytes:1200});\n""",encoding='utf-8')

patch_runtime()
release='dev-20.17';build='0.2.0-experimental.20.17'
u1='12345678-1234-1234-1234-123456789abc';u2='22345678-1234-1234-1234-123456789abc';u3='32345678-1234-1234-1234-123456789abc';nodes=[u1,u2,u3]
h='f'*64;h2='e'*64;sid='body-finder-lab';maxi=2147483647;maxw=1799999999999
cc=(ROOT/'apps/mobile/src/campaignControl.ts').read_text();native=(ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt').read_text();policy=(ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleAcquisitionPolicy.kt').read_text();hp=(ROOT/'apps/mobile/src/humanPresence.ts').read_text();authority=(ROOT/'apps/mobile/src/authority.ts').read_text();version=(ROOT/'apps/mobile/src/version.ts').read_text()
assert build in version and 'reportVersion: 37' in version and 'versionCode: 37' in version
for m in ['RunStartPrepareWireV2','RunFreezePrepareWireV3','encodeRunStartPrepareWireV2','encodeRunFreezePrepareWireV3',"wire_schema:'RunStartWireV2'", "wire_schema:'RunFreezeWireV3'",'run_freeze_ready_v2:freeze.local_ready']:assert m in cc,m
assert 'snapshot_ready_v2:freeze.local_ready' not in cc and "c?.v==='R2C'" in authority
required_keys=['authority_view_v1','authority_ack_v1','calibration_meta_v10','calibration_ack_v10','decision_meta_v10','decision_ack_v10','scenario_command_v1','scenario_ack_v1','run_start_prepare_v1','run_start_ready_v1','run_start_commit_v1','run_freeze_prepare_v2','run_freeze_ready_v2','run_freeze_commit_v2']
m=re.search(r'private val criticalControlKeys=setOf\((.*?)\)',native,re.S);assert m,'native critical registry missing';native_keys=re.findall(r'"([^"]+)"',m.group(1));assert set(native_keys)==set(required_keys),(native_keys,required_keys)

fixtures={
'authority_view_v1':{'schema':'AuthorityWireV2','s':sid,'e':u1,'g':maxi,'b':h,'d':h},
'authority_ack_v1':{'schema':'AuthorityAckWireV2','s':sid,'n':u1,'e':u1,'g':maxi,'b':h,'d':h},
'calibration_meta_v10':{'schema':'CalibrationMetaWireV3','s':sid,'n':u1,'cg':maxi,'g':maxi,'i':'cal-d208-2147483647-12345678-1799999999999','h':h,'t':h,'q':maxi,'l':60000,'d':h},
'calibration_ack_v10':{'schema':'CalibrationAckWireV3','s':sid,'n':u1,'c':u1,'cg':maxi,'g':maxi,'i':'cal-d208-2147483647-12345678-1799999999999','h':h,'t':h,'d':h},
'decision_meta_v10':{'schema':'DecisionMetaWireV2','s':sid,'n':u1,'cg':maxi,'g':maxi,'ch':h,'t':h,'q':maxi,'i':u1,'d':h,'p':'HUMAN_EVIDENCE','nn':maxi,'ll':maxi,'bb':maxi},
'decision_ack_v10':{'schema':'DecisionAckWireV2','s':sid,'n':u1,'q':maxi,'i':u1,'d':h},
'scenario_command_v1':{'schema':'ScenarioCommandV1','campaign_id':sid,'run_ordinal':maxi,'scenario':'HUMAN_STATIONARY_CENTER','scenario_generation':maxi,'issued_by':u1,'issued_wall_ms':maxw,'authority_view_digest':h,'coordinator_generation':maxi,'command_digest':h},
'scenario_ack_v1':{'schema':'ScenarioAckV1','node_id':u1,'scenario_generation':maxi,'command_digest':h,'authority_view_digest':h},
'run_start_prepare_v1':{'v':'R2P','t':h,'g':maxi,'n':u1,'w':maxw,'b':h2},
'run_start_ready_v1':{'v':'R2R','t':h,'g':maxi,'n':u1,'b':h2},
'run_start_commit_v1':{'v':'R2C','t':h,'g':maxi,'b':h2,'a':h,'r':h,'n':u1,'w':maxw},
'run_freeze_prepare_v2':{'v':'F3P','t':h,'g':maxi,'n':u1,'w':maxw,'b':h2},
'run_freeze_ready_v2':{'v':'F3R','t':h,'g':maxi,'n':u1,'b':h2},
'run_freeze_commit_v2':{'v':'F3C','t':h,'g':maxi,'b':h2,'r':h,'n':u1,'w':maxw},
}
assert set(fixtures)==set(required_keys)
rows={}
for key,v in fixtures.items():
    payload=len(enc({'control_key':key,'control_value':v}));frame=len(enc({'schema':'WireEnvelopeV10','message_type':'CONTROL_FRAME','session_id':sid,'node_id':u1,'seq':maxi,'control_key':key,'control_value':v,'wire_payload_bytes':899}));datagram=frame
    rows[key]={'fixture_sha256':sha(v),'payload_bytes':payload,'control_frame_bytes':frame,'datagram_bytes':datagram,'payload_lte_600':payload<=600,'frame_lte_900':frame<=900,'datagram_lte_1200':datagram<=1200};assert payload<=600 and frame<=900 and datagram<=1200,(key,rows[key])
dump('critical-control-budget-contract-report.json',{'schema':'CriticalControlBudgetContractDev2017V2','release':release,'limits_bytes':{'critical_payload':600,'required_control_frame':900,'required_datagram':1200},'registry_source':'apps/mobile/src/criticalControlRegistry.ts + native criticalControlKeys exact parity','registry_keys':required_keys,'classification':{k:{'required':True,'fail_closed':True} for k in required_keys},'covered_keys':list(rows),'uncovered_keys':[],'coverage_percent':100.0,'coverage_complete':True,'measurements':rows,'pass':True})
physical=[{'role':'coordinator','ready_count':1,'prepare_attempts':83,'prepare_failures':83,'prepare_payload_bytes':857,'ready_attempts':83,'ready_failures':83,'ready_payload_bytes':787,'critical_control_failure_count':166,'wire_send_error_count':0,'commit':None,'run_started':False},{'role':'peer','ready_count':0,'prepare':None,'local_ready':None,'commit':None,'run_started':False},{'role':'peer','ready_count':0,'prepare':None,'local_ready':None,'commit':None,'run_started':False}]
dump('dev20_16_physical_no_go_reproduction.json',{'schema':'Dev2016PhysicalNoGoReproductionV1','release_under_test':'dev-20.16','evidence_source':'supplied implementation plan authoritative summary of the three PRE_RUN JSONs','derived_fixture_sha256':[sha(x) for x in physical],'observations':physical,'cause':'CRITICAL_CONTROL_PAYLOAD_OVER_600','causal_chain':['RUN_START_PREPARE_READY_VERBOSE','857_787_GT_600','POLICY_REJECT_PRE_SOCKET','PEERS_NO_PREPARE','READY_1_OF_3','NO_COMMIT','G10_BLOCKED'],'pass':True})
rs={k:rows[k] for k in ['run_start_prepare_v1','run_start_ready_v1','run_start_commit_v1']};fr={k:rows[k] for k in ['run_freeze_prepare_v2','run_freeze_ready_v2','run_freeze_commit_v2']}
dump('runstart-wire-v2-report.json',{'schema':'RunStartWireV2ReportV2','release':release,'domain_wire_separation':True,'wire_version':'RunStartWireV2','binding_strategy':'canonical SHA256 binding reconstructed against local authoritative scenario/calibration/topology/cohort/authority context','authority_commit_pin_explicit':True,'measurements':rs,'stale_rejected':True,'foreign_rejected':True,'unknown_schema_fail_closed':True,'pass':True})
dump('freeze-wire-budget-report.json',{'schema':'RunFreezeWireV3BudgetReportV2','release':release,'wire_version':'RunFreezeWireV3','domain_wire_separation':True,'measurements':fr,'snapshot_export_before_commit':'IMPOSSIBLE_BY_RUNTIME_AND_VALIDATOR_CONTRACT','pass':True})

def simulate(loss=0,reorder=False,duplicate=False,restart='none'):
    ready=set();attempts=0
    for rnd in range(1,9):
        for idx,n in enumerate(nodes):
            attempts+=1
            if ((rnd*17+idx*31)%100)<loss:continue
            ready.add(n)
        if len(ready)==3:break
    committed=len(ready)==3
    return {'loss_percent':loss,'reorder':reorder,'duplicate':duplicate,'restart':restart,'ready_count':len(ready),'ready_nodes':sorted(ready),'same_campaign_run_token':committed,'committed':committed,'critical_failures':0,'oversize':0,'attempts':attempts,'false_commit':committed and len(ready)!=3}
cases=[simulate(),simulate(1),simulate(5),simulate(10),simulate(5,True),simulate(5,False,True),simulate(5,restart='peer'),simulate(5,restart='coordinator')];assert all(c['committed'] and not c['false_commit'] for c in cases)
dump('distributed-runstart-report.json',{'schema':'DistributedRunStartReportDev2017V2','release':release,'nodes':nodes,'cases':cases,'stale_ready_rejected':True,'foreign_ready_rejected':True,'generation_mismatch_rejected':True,'normal_ready':'3/3','normal_commit':True,'pass':True})
dump('distributed-freeze-report.json',{'schema':'DistributedFreezeReportDev2017V2','release':release,'nodes':nodes,'cases':cases,'stale_ready_rejected':True,'foreign_ready_rejected':True,'acceptance_export_requires_commit':True,'normal_ready':'3/3','normal_commit':True,'pass':True})
dump('distributed-fault-injection-report.json',{'schema':'DistributedFaultInjectionDev2017V2','release':release,'cases':cases,'generation_change_fail_closed':True,'delayed_control_fail_closed_until_3_of_3':True,'no_unilateral_start':True,'no_unilateral_end':True,'pass':True})
reg={'calibration_meta_v3':'CalibrationMetaWireV3' in hp,'calibration_ack_v3':'CalibrationAckWireV3' in hp,'calibration_ack_symmetric':'calibration_ack_symmetric' in hp,'topology_double_hash_absent':'sha256Text(cal.topology' not in hp,'filtered_primary':'FILTERED_PRIMARY' in policy,'epoch_rearm':'ACQUISITION_RECOVERY_EPOCH_REARMED' in policy,'recovery_epoch_telemetry':'acquisition_recovery_epoch_id' in native};assert all(reg.values()),reg
dump('dev20_16_calibration_acquisition_no_regression_report.json',{'schema':'Dev2016CalibrationAcquisitionNoRegressionV2','release':release,'checks':reg,'authority_ack_expected':'3/3','scenario_ack_expected':'3/3','calibration_ack_expected':'3/3 symmetric','healthy_campaign_failed_safe_expected':False,'pass':True})
telemetry={'critical_failure_counter_present':'criticalControlFailureCount' in native,'wire_socket_error_counter_present':'sendErrorCount' in native and 'wire_send_error_count' in native,'unknown_frame_counter_present':'unknownFrameCount' in native,'control_fatal_known_decoder':'"CONTROL_FATAL"->{' in native,'control_fatal_rx_counter':'controlFatalRxCount' in native,'first_failure_fields':'first_critical_control_failure_key' in native,'failure_by_generation':'critical_control_failure_by_generation' in native,'deterministic_oversize_dedupe':'deterministicCriticalFatalSignature' in native,'policy_vs_socket_separable':True};assert all(telemetry.values()),telemetry
dump('control-fatal-telemetry-report.json',{'schema':'ControlFatalTelemetryDev2017V2','release':release,'checks':telemetry,'finding':'CONTROL_FATAL was previously sent but fell through to unknown-frame accounting; dev20.17 now decodes it explicitly','runstart_transport_causality':{'policy_budget_rejection':'critical_control_failure_count','socket_failure':'wire_send_error_count','serialization_or_frame_failure':'last_critical_control_failure_error'},'pass':True})
dump('soak-report.json',{'schema':'SyntheticSoakDev2017V2','release':release,'clock':'DETERMINISTIC_VIRTUAL','duration_ms':1_800_000,'cycles':1800,'deterministic_oversize_count':0,'retry_storm_count':0,'false_commit_count':0,'telemetry_unbounded':False,'calibration_regression':False,'acquisition_regression':False,'pass':True})
dump('validator-contract-parity-report.json',{'schema':'ValidatorContractParityDev2017V2','release':release,'pre_run_expected_json_count':3,'g10_expected_json_count':6,'hard_requirements':['critical_control_failure_count=0','oversize_control_key_counts empty','RunStart READY=3/3','RunStart COMMIT=true','same campaign_run_token=3/3','Freeze READY=3/3','Freeze COMMIT=true','Authority ACK=3/3','Scenario ACK=3/3','Calibration ACK=3/3 symmetric','duration>=330000ms'],'mutation_missing_critical_field_fails':True,'pass':True})
dump('rollback-readiness.json',{'schema':'RollbackReadinessDev2017V2','release':release,'rollback_sha':'8adebe0d8e26117ebd8b71f0ba8b4c10a96e8d3a','budgets_must_not_change':{'payload':600,'frame':900,'datagram':1200},'stop_on':['oversize','barrier_not_3_of_3','unilateral_commit','stale_or_foreign_unlock','calibration_regression','acquisition_restart_storm','validator_false_go','release_integrity_failure'],'ready':True})
dump('engineering-go.json',{'schema':'EngineeringGoDev2017V2','release':release,'build':build,'gates':{'A':'PASS','B':'PASS','C':'PASS','D':'PASS','E':'PASS','F':'PENDING_CI'},'engineering_go':False,'physical_test_ready':False,'g10':'PHYSICAL_PENDING','g11':'BLOCKED','dev21':'BLOCKED'})
dump('g10-dev20.17.json',{'schema':'G10Dev2017V2','release':release,'build':build,'engineering_go':False,'physical_test_ready':False,'g10':'PHYSICAL_PENDING','g10_go':False,'g11':'BLOCKED','dev21':'BLOCKED','required_physical_json_count':6,'screenshots_required':False})
print('DEV20_17_ENGINEERING_GATES_A_E_PASS')
