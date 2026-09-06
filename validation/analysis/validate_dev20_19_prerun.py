#!/usr/bin/env python3
"""Strict dev-20.19 exactly-three-node PRE_RUN validator. JSON only."""
from __future__ import annotations
import argparse,json,re,sys
from pathlib import Path
from typing import Any

RELEASE="dev-20.19"; BUILD="0.2.0-experimental.20.19"; EVIDENCE="v21"; REPORT=39; SNAPSHOT=21
HEX64=re.compile(r"^[0-9a-fA-F]{64}$")

def load(p:Path,errors:list[str])->dict[str,Any]:
    try:
        d=json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(d,dict): raise ValueError("root must be object")
        return d
    except Exception as e:
        errors.append(f"INVALID_JSON:{p.name}:{e}"); return {}

def as_int(v:Any,default=-1):
    try:return int(v)
    except:return default

def as_bool(v:Any):
    if isinstance(v,bool):return v
    if isinstance(v,(int,float)):return bool(v)
    return isinstance(v,str) and v.strip().lower() in {"true","1","yes","ready","go","pass","committed","commit","healthy","valid"}

def walk(v:Any):
    if isinstance(v,dict):
        yield v
        for x in v.values(): yield from walk(x)
    elif isinstance(v,list):
        for x in v: yield from walk(x)

def metadata_gate(d:dict[str,Any],name:str,errors:list[str]):
    expected={"release":RELEASE,"build":BUILD,"evidence_schema":EVIDENCE,"report_version":REPORT,"snapshot_schema_version":SNAPSHOT}
    for k,v in expected.items():
        if d.get(k)!=v: errors.append(f"METADATA_{k.upper()}_MISMATCH:{name}:{d.get(k)!r}")
    if d.get("artifact_build_identity")!=f"{RELEASE}:{BUILD}": errors.append(f"ARTIFACT_BUILD_IDENTITY_MISMATCH:{name}")
    dc=d.get("diagnostic_contract") or {}; ec=d.get("evidence_contract") or {}
    if isinstance(dc,dict) and dc.get("schema")!="dev20.19-diagnostic-contract-v21": errors.append(f"DIAGNOSTIC_CONTRACT_MISMATCH:{name}:{dc.get('schema')!r}")
    if isinstance(ec,dict) and ec.get("schema")!="dev20.19-state-lifecycle-json-evidence-v21": errors.append(f"EVIDENCE_CONTRACT_MISMATCH:{name}:{ec.get('schema')!r}")
    if d.get("evidence_contract_version")!="dev20.19-state-lifecycle-json-evidence-v21": errors.append(f"EVIDENCE_CONTRACT_VERSION_MISMATCH:{name}:{d.get('evidence_contract_version')!r}")
    for obj in walk(d):
        for k,v in obj.items():
            if k=="release" and isinstance(v,str) and v.startswith("dev-20.") and v!=RELEASE: errors.append(f"CONTRADICTORY_RELEASE:{name}:{v}")
            if k=="build" and isinstance(v,str) and v.startswith("0.2.0-experimental.20.") and v!=BUILD: errors.append(f"CONTRADICTORY_BUILD:{name}:{v}")
            if k=="evidence_schema" and v!=EVIDENCE: errors.append(f"CONTRADICTORY_EVIDENCE_SCHEMA:{name}:{v!r}")
            if k=="report_version" and as_int(v)!=REPORT: errors.append(f"CONTRADICTORY_REPORT_VERSION:{name}:{v!r}")
            if k=="snapshot_schema_version" and as_int(v)!=SNAPSHOT: errors.append(f"CONTRADICTORY_SNAPSHOT_SCHEMA:{name}:{v!r}")
            if k=="schema" and isinstance(v,str) and "dev20." in v.lower() and "dev20.19" not in v.lower(): errors.append(f"CONTRADICTORY_DEV20_SCHEMA:{name}:{v}")

def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument("files",nargs="*"); ap.add_argument("--output"); ns=ap.parse_args(argv)
    paths=[Path(x) for x in ns.files]; errors=[]
    if len(paths)!=3: errors.append(f"EXACTLY_3_FILES_REQUIRED:{len(paths)}")
    docs=[load(p,errors) for p in paths]
    nodes=[]; cal_ids=[]; cal_hashes=[]; cal_gens=[]; topo=[]; bindings=[]; authority=[]; tokens=[]; cohorts=[]
    for p,d in zip(paths,docs):
        if not d: continue
        metadata_gate(d,p.name,errors)
        node=str(d.get("node_id") or ""); nodes.append(node)
        if not node: errors.append(f"NODE_ID_REQUIRED:{p.name}")
        a=d.get("authority_status") or {}; view=a.get("view") or {}
        if not as_bool(a.get("consensus")) or as_int(a.get("ack_count"))!=3: errors.append(f"AUTHORITY_EXACT_3_OF_3_REQUIRED:{p.name}")
        authority.append(str(view.get("authority_view_digest") or ""))
        cohort=view.get("cohort") or []; cohorts.append(tuple(sorted(str(x.get("node_id")) for x in cohort if isinstance(x,dict))))
        g=d.get("geometry_summary") or {}
        if str(g.get("state") or "").upper()!="GEOMETRY_2D": errors.append(f"GEOMETRY_2D_REQUIRED:{p.name}")
        c=d.get("calibration_status") or {}
        if str(c.get("state") or "").upper()!="READY": errors.append(f"CURRENT_CALIBRATION_READY_REQUIRED:{p.name}:{c.get('state')!r}")
        ack=as_int(c.get("current_calibration_ack_count",c.get("peer_ack_count")))
        if ack!=3 or as_int(c.get("peer_ack_count",ack))!=3: errors.append(f"CALIBRATION_ACK_EXACT_3_OF_3_REQUIRED:{p.name}:{ack}")
        if not as_bool(c.get("calibration_ack_symmetric")): errors.append(f"CALIBRATION_ACK_SYMMETRIC_REQUIRED:{p.name}")
        if not as_bool(c.get("distributed_calibration_ready")): errors.append(f"DISTRIBUTED_CALIBRATION_READY_REQUIRED:{p.name}")
        if not as_bool(c.get("local_artifact_promoted")): errors.append(f"LOCAL_VERIFIED_ARTIFACT_PROMOTED_REQUIRED:{p.name}")
        if str(c.get("artifact_promotion_state") or "")!="PROMOTED": errors.append(f"ARTIFACT_PROMOTION_STATE_REQUIRED:{p.name}")
        cid=str(c.get("calibration_id") or ""); ch=str(c.get("calibration_hash") or ""); gen=as_int(c.get("calibration_generation",c.get("generation"))); th=str(c.get("topology_hash") or ""); bd=str(c.get("current_calibration_binding_digest") or "")
        cal_ids.append(cid);cal_hashes.append(ch);cal_gens.append(gen);topo.append(th);bindings.append(bd)
        if not cid or not ch or gen<=0 or not HEX64.fullmatch(th) or not HEX64.fullmatch(bd): errors.append(f"CALIBRATION_IDENTITY_INCOMPLETE:{p.name}")
        s=d.get("scenario_status") or {}
        if as_int(s.get("ack_count"))!=3 or not as_bool(s.get("ready")): errors.append(f"SCENARIO_EXACT_3_OF_3_REQUIRED:{p.name}")
        r=d.get("run_start") or {}
        if as_int(r.get("ready_count"))!=3 or not as_bool(r.get("committed")): errors.append(f"RUNSTART_READY_3_AND_COMMIT_REQUIRED:{p.name}")
        token=str(((r.get("commit") or {}).get("campaign_run_token")) or ((r.get("prepare") or {}).get("campaign_run_token")) or ""); tokens.append(token)
        if not HEX64.fullmatch(token): errors.append(f"RUNSTART_TOKEN_SHA256_REQUIRED:{p.name}")
        wt=d.get("wire_transport_telemetry") or d.get("wire_transport_telemetry_v13") or ((d.get("fabric_diagnostics") or {}).get("wire_transport_v11")) or {}
        if as_int(wt.get("critical_control_payload_target_bytes"))!=600 or as_int(wt.get("control_frame_target_bytes"))!=900 or as_int(wt.get("max_datagram_budget_bytes"))!=1200: errors.append(f"WIRE_BUDGET_CONTRACT_MISMATCH:{p.name}")
        if as_int(wt.get("critical_control_failure_count"),0)!=0: errors.append(f"CRITICAL_CONTROL_FAILURE:{p.name}:{wt.get('critical_control_failure_count')}")
        if as_int(wt.get("required_frame_oversize_count"),0)!=0: errors.append(f"REQUIRED_FRAME_OVERSIZE:{p.name}")
        ov=wt.get("oversize_control_key_counts") or {}
        if isinstance(ov,dict) and any(as_int(v,0)!=0 for v in ov.values()): errors.append(f"CRITICAL_CONTROL_OVERSIZE:{p.name}:{ov}")
        cm=as_int((wt.get("max_control_payload_bytes_by_key") or {}).get("calibration_meta_v10"),0)
        if cm>560: errors.append(f"CALIBRATION_META_ENGINEERING_TARGET_EXCEEDED:{p.name}:{cm}")
    if len(set(x for x in nodes if x))!=3: errors.append("EXACTLY_3_UNIQUE_NODES_REQUIRED")
    for label,values in [("CALIBRATION_ID",cal_ids),("CALIBRATION_HASH",cal_hashes),("CALIBRATION_GENERATION",cal_gens),("TOPOLOGY_HASH",topo),("CALIBRATION_BINDING",bindings),("AUTHORITY_DIGEST",authority),("RUNSTART_TOKEN",tokens),("COHORT",cohorts)]:
        if len(values)!=3 or len(set(values))!=1 or values[0] in ("",-1,()): errors.append(f"{label}_PARITY_3_OF_3_REQUIRED")
    out={"schema":"PreRunDev2019PhysicalValidationV1","release":RELEASE,"build":BUILD,"files":len(paths),"unique_nodes":sorted(set(x for x in nodes if x)),"errors":sorted(set(errors)),"pre_run":"GO" if not errors else "NO_GO","pre_run_go":not errors,"screenshots_required":False,"next_step":"RUN_G10" if not errors else "STOP_AND_SHARE_EXACTLY_3_PRE_RUN_JSON"}
    text=json.dumps(out,indent=2,sort_keys=True); print(text)
    if ns.output: Path(ns.output).write_text(text+"\n",encoding="utf-8")
    return 0 if not errors else 2

if __name__=="__main__": sys.exit(main())
