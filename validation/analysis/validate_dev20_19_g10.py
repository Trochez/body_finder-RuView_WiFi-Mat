#!/usr/bin/env python3
"""Strict dev-20.19 G10 validator: exactly six fresh JSONs; screenshots are ignored."""
from __future__ import annotations
import argparse,hashlib,json,re,sys
from pathlib import Path
from typing import Any

RELEASE="dev-20.19"; BUILD="0.2.0-experimental.20.19"; EVIDENCE="v21"; REPORT=39; SNAPSHOT=21
MIN_DURATION_MS=330_000; MAX_PRIMARY_AGE_MS=5_000; MAX_RESTARTS_PER_330S=6
HEX64=re.compile(r"^[0-9a-fA-F]{64}$")

def walk(o:Any):
    if isinstance(o,dict):
        yield o
        for v in o.values():yield from walk(v)
    elif isinstance(o,list):
        for v in o:yield from walk(v)

def vals(o:Any,*keys:str):
    wanted={k.lower() for k in keys};out=[]
    for d in walk(o):
        for k,v in d.items():
            if str(k).lower() in wanted:out.append(v)
    return out

def first(o:Any,*keys:str,default=None):
    v=vals(o,*keys); return v[0] if v else default

def ai(v,default=-1):
    try:return int(v)
    except:return default

def ab(v):
    if isinstance(v,bool):return v
    if isinstance(v,(int,float)):return bool(v)
    return isinstance(v,str) and v.strip().lower() in {"true","1","yes","ready","go","pass","committed","commit","healthy","valid"}

def ss(v):return "" if v is None else str(v).strip()

def load(p:Path,errors:list[str]):
    try:
        d=json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(d,dict):raise ValueError("root must be object")
        return d
    except Exception as e:errors.append(f"INVALID_JSON:{p.name}:{e}");return {}

def metadata_gate(d:dict[str,Any],name:str,errors:list[str]):
    for k,v in {"release":RELEASE,"build":BUILD,"evidence_schema":EVIDENCE,"report_version":REPORT,"snapshot_schema_version":SNAPSHOT}.items():
        if d.get(k)!=v:errors.append(f"METADATA_{k.upper()}_MISMATCH:{name}:{d.get(k)!r}")
    if d.get("artifact_build_identity")!=f"{RELEASE}:{BUILD}":errors.append(f"ARTIFACT_BUILD_IDENTITY_MISMATCH:{name}")
    ec=d.get("evidence_contract") or {}; dc=d.get("diagnostic_contract") or {}
    if not isinstance(ec,dict) or ec.get("schema")!="dev20.19-state-lifecycle-json-evidence-v21":errors.append(f"EVIDENCE_CONTRACT_MISMATCH:{name}")
    if not isinstance(dc,dict) or dc.get("schema")!="dev20.19-diagnostic-contract-v21":errors.append(f"DIAGNOSTIC_CONTRACT_MISMATCH:{name}")
    for obj in walk(d):
        for k,v in obj.items():
            if k=="release" and isinstance(v,str) and v.startswith("dev-20.") and v!=RELEASE:errors.append(f"CONTRADICTORY_RELEASE:{name}:{v}")
            if k=="build" and isinstance(v,str) and v.startswith("0.2.0-experimental.20.") and v!=BUILD:errors.append(f"CONTRADICTORY_BUILD:{name}:{v}")
            if k=="evidence_schema" and v!=EVIDENCE:errors.append(f"CONTRADICTORY_EVIDENCE_SCHEMA:{name}:{v!r}")
            if k=="schema" and isinstance(v,str) and "dev20." in v.lower() and "dev20.19" not in v.lower():errors.append(f"CONTRADICTORY_DEV20_SCHEMA:{name}:{v}")

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument("files",nargs="*");ap.add_argument("--output");ns=ap.parse_args(argv)
    paths=[Path(x) for x in ns.files];errors=[]
    if len(paths)!=6:errors.append(f"EXACTLY_6_FILES_REQUIRED:{len(paths)}")
    docs=[load(p,errors) for p in paths]
    rows=[]
    for p,d in zip(paths,docs):
        if not d:continue
        metadata_gate(d,p.name,errors)
        if d.get("evidence_class")=="PRE_RUN_DIAGNOSTIC_V1" or first(d,"evidence_phase","capture_phase","run_phase") in {"PRE_RUN","pre_run"}:errors.append(f"PRE_RUN_NOT_ACCEPTANCE:{p.name}")
        duration=ai(first(d,"duration_ms","run_duration_ms","elapsed_ms"),0)
        if duration<MIN_DURATION_MS:errors.append(f"DURATION_LT_{MIN_DURATION_MS}:{p.name}:{duration}")
        scenario=ss(first(d,"scenario","scenario_id","scenario_name","validation_scenario"))
        node=ss(first(d,"node_id","local_node_id","device_node_id")); session=ss(first(d,"session_id","validation_session_id"))
        if not node:errors.append(f"NODE_ID_REQUIRED:{p.name}")
        if not session:errors.append(f"SESSION_ID_REQUIRED:{p.name}")
        if ai(first(d,"authority_ack_count","authority_ready_count","authority_ack"))!=3:errors.append(f"AUTHORITY_ACK_3_REQUIRED:{p.name}")
        geom=ss(first(d,"geometry_state","geometry_mode"));
        if geom.upper()!="GEOMETRY_2D":errors.append(f"GEOMETRY_2D_REQUIRED:{p.name}:{geom}")
        state=ss(first(d,"calibration_state")); ack=ai(first(d,"current_calibration_ack_count","peer_ack_count","calibration_ack_count"))
        if state.upper()!="READY":errors.append(f"CALIBRATION_READY_REQUIRED:{p.name}:{state}")
        if ack!=3 or not ab(first(d,"calibration_ack_symmetric")) or not ab(first(d,"distributed_calibration_ready")):errors.append(f"CALIBRATION_EXACT_3_OF_3_REQUIRED:{p.name}:{ack}")
        promoted=first(d,"local_artifact_promoted")
        if promoted is not None and not ab(promoted):errors.append(f"LOCAL_ARTIFACT_PROMOTION_REQUIRED:{p.name}")
        cid=ss(first(d,"calibration_id")); ch=ss(first(d,"calibration_hash")); cg=ai(first(d,"calibration_generation")); th=ss(first(d,"topology_hash")); coord=ss(first(d,"coordinator_node_id","coordinator_id")); cgen=ai(first(d,"coordinator_generation")); auth=ss(first(d,"authority_digest","authority_view_digest"))
        if not cid or not ch or cg<=0 or not HEX64.fullmatch(th) or not coord or cgen<=0 or not HEX64.fullmatch(auth):errors.append(f"CURRENT_BINDING_IDENTITY_REQUIRED:{p.name}")
        if ai(first(d,"scenario_ack_count","scenario_ready_count"))!=3:errors.append(f"SCENARIO_ACK_3_REQUIRED:{p.name}")
        if ai(first(d,"runstart_ready_count","run_start_ready_count","run_start_ack_count"))!=3 or not ab(first(d,"runstart_commit","run_start_commit","run_start_committed","committed")):errors.append(f"RUNSTART_READY_3_COMMIT_REQUIRED:{p.name}")
        token=ss(first(d,"campaign_run_token","run_start_token"));
        if not HEX64.fullmatch(token):errors.append(f"RUNSTART_TOKEN_SHA256_REQUIRED:{p.name}")
        if ai(first(d,"freeze_ready_count","snapshot_ready_count","freeze_ack_count"))!=3 or not ab(first(d,"freeze_commit","snapshot_commit","freeze_committed","distributed_freeze_committed")):errors.append(f"FREEZE_READY_3_COMMIT_REQUIRED:{p.name}")
        failures=ai(first(d,"critical_control_failure_count","critical_control_failures"),0)
        if failures!=0:errors.append(f"CRITICAL_CONTROL_FAILURE:{p.name}:{failures}")
        overs=first(d,"oversize_control_key_counts","critical_control_oversize_counts") or {}
        if isinstance(overs,dict) and any(ai(v,0)!=0 for v in overs.values()):errors.append(f"CRITICAL_CONTROL_OVERSIZE:{p.name}:{overs}")
        required_overs=ai(first(d,"required_frame_oversize_count"),0)
        if required_overs!=0:errors.append(f"REQUIRED_FRAME_OVERSIZE:{p.name}:{required_overs}")
        maxcal=first(d,"max_control_payload_bytes_by_key")
        if isinstance(maxcal,dict) and ai(maxcal.get("calibration_meta_v10"),0)>560:errors.append(f"CALIBRATION_META_GT_560:{p.name}:{maxcal.get('calibration_meta_v10')}")
        strategy=ss(first(d,"acquisition_strategy","ble_acquisition_strategy","strategy")).upper()
        if not strategy or strategy in {"FAILED_SAFE","RECOVERING","UNFILTERED_RECOVERY","FILTERED_RECOVERY_PROBE"}:errors.append(f"ACQUISITION_NOT_READY:{p.name}:{strategy}")
        if ab(first(d,"recovery_budget_exhausted","acquisition_recovery_budget_exhausted")):errors.append(f"RECOVERY_BUDGET_EXHAUSTED:{p.name}")
        if ab(first(d,"restart_storm_detected","scanner_restart_storm")):errors.append(f"RESTART_STORM:{p.name}")
        rd=first(d,"scanner_restart_delta","filtered_scanner_restart_count_delta","scanner_restart_count_delta")
        if rd is not None and ai(rd)>MAX_RESTARTS_PER_330S:errors.append(f"RESTART_DELTA_EXCESS:{p.name}:{rd}")
        age=first(d,"last_successful_primary_observation_age_ms","primary_observation_age_ms","primary_metric_age_ms")
        if age is None or ai(age)>MAX_PRIMARY_AGE_MS:errors.append(f"PRIMARY_METRIC_STALE_OR_MISSING:{p.name}:{age}")
        fg=first(d,"foreground_valid","foreground_validity","foreground_interval_valid")
        if fg is None or not ab(fg):errors.append(f"FOREGROUND_VALID_REQUIRED:{p.name}:{fg}")
        cohort=first(d,"expected_cohort","cohort_node_ids")
        cohort=tuple(sorted(map(str,cohort))) if isinstance(cohort,list) else ()
        rows.append({"file":p.name,"scenario":scenario,"node":node,"session":session,"cohort":cohort,"calibration":(cid,ch,cg,th,coord,cgen,auth),"token":token})
    empty=[r for r in rows if "EMPTY" in r["scenario"].upper() and "HUMAN" not in r["scenario"].upper()]
    human=[r for r in rows if "HUMAN_MOVING" in r["scenario"].upper()]
    if len(empty)!=3 or len(human)!=3:errors.append(f"SCENARIOS_EXACT_3_EMPTY_3_HUMAN_REQUIRED:empty={len(empty)}:human={len(human)}")
    if len({r["node"] for r in rows if r["node"]})!=3:errors.append("EXACTLY_3_UNIQUE_NODES_REQUIRED")
    if rows and len({r["calibration"] for r in rows})!=1:errors.append("CALIBRATION_AUTHORITY_TOPOLOGY_PARITY_ALL_6_REQUIRED")
    if rows and len({r["cohort"] for r in rows})!=1:errors.append("COHORT_PARITY_ALL_6_REQUIRED")
    for label,group in [("EMPTY",empty),("HUMAN_MOVING",human)]:
        if len(group)==3:
            if len({r["node"] for r in group})!=3:errors.append(f"{label}_EXACTLY_3_NODES_REQUIRED")
            if len({r["session"] for r in group})!=1:errors.append(f"{label}_SESSION_PARITY_REQUIRED")
            if len({r["token"] for r in group})!=1:errors.append(f"{label}_RUNSTART_TOKEN_PARITY_3_OF_3_REQUIRED")
    if len(empty)==3 and len(human)==3 and empty[0]["token"]==human[0]["token"]:errors.append("FRESH_RUNSTART_REQUIRED_BETWEEN_SCENARIOS")
    out={"schema":"G10Dev2019PhysicalValidationV1","release":RELEASE,"build":BUILD,"files":len(paths),"unique_nodes":sorted({r['node'] for r in rows if r['node']}),"scenarios":{"EMPTY":len(empty),"HUMAN_MOVING":len(human)},"minimum_duration_ms":MIN_DURATION_MS,"errors":sorted(set(errors)),"g10":"GO" if not errors else "NO_GO","g10_go":not errors,"g11":"UNBLOCKED" if not errors else "BLOCKED","dev21":"UNBLOCKED" if not errors else "BLOCKED","final_go":not errors,"screenshots_required":False}
    text=json.dumps(out,indent=2,sort_keys=True);print(text)
    if ns.output:Path(ns.output).write_text(text+"\n",encoding="utf-8")
    return 0 if not errors else 2

if __name__=="__main__":sys.exit(main())
