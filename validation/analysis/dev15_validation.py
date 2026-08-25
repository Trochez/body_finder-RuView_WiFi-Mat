#!/usr/bin/env python3
from __future__ import annotations
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

RECOVERY_TYPES = {"RECOVERY_REQUESTED", "FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY", "RECOVERY_SUCCESS", "RECOVERY_FAILURE"}
STAGES = {"LONG_1", "LONG_2", "SHORT", "LONG_POST_SHORT"}

class ContractError(Exception):
    def __init__(self, code: str, path: str):
        super().__init__(f"{code}:{path}")
        self.code = code
        self.path = path

def require_field(obj: dict, key: str, path: str = "$") -> Any:
    if not isinstance(obj, dict) or key not in obj:
        raise ContractError("MISSING_REQUIRED_FIELD", f"{path}.{key}")
    return obj[key]

def require_dict(obj: dict, key: str, path: str = "$") -> dict:
    value = require_field(obj, key, path)
    if not isinstance(value, dict): raise ContractError("INVALID_TYPE_DICT", f"{path}.{key}")
    return value

def require_list(obj: dict, key: str, path: str = "$") -> list:
    value = require_field(obj, key, path)
    if not isinstance(value, list): raise ContractError("INVALID_TYPE_LIST", f"{path}.{key}")
    return value

def require_bool(obj: dict, key: str, path: str = "$") -> bool:
    value = require_field(obj, key, path)
    if type(value) is not bool: raise ContractError("INVALID_TYPE_BOOL", f"{path}.{key}")
    return value

def require_int(obj: dict, key: str, path: str = "$") -> int:
    value = require_field(obj, key, path)
    if type(value) is not int: raise ContractError("INVALID_TYPE_INT", f"{path}.{key}")
    return value

def require_number(obj: dict, key: str, path: str = "$") -> float:
    value = require_field(obj, key, path)
    if type(value) not in (int, float): raise ContractError("INVALID_TYPE_NUMBER", f"{path}.{key}")
    return float(value)

def require_string(obj: dict, key: str, path: str = "$") -> str:
    value = require_field(obj, key, path)
    if not isinstance(value, str) or not value: raise ContractError("INVALID_TYPE_STRING", f"{path}.{key}")
    return value

def unwrap_export(doc: dict) -> tuple[dict, dict]:
    if not isinstance(doc, dict): raise ContractError("INVALID_EXPORT", "$")
    return doc, require_dict(doc, "validation_run")

def _recovery_analysis(run: dict):
    errors = []
    events = require_list(run, "events", "$.validation_run")
    normalized = []
    for i, event in enumerate(events):
        if not isinstance(event, dict):
            errors.append(f"INVALID_EVENT_TYPE:{i}")
            continue
        try:
            typ = require_string(event, "type", f"$.validation_run.events[{i}]")
            require_int(event, "seq", f"$.validation_run.events[{i}]")
            require_number(event, "wall_ms", f"$.validation_run.events[{i}]")
            if typ in RECOVERY_TYPES:
                generation = require_field(event, "recovery_generation", f"$.validation_run.events[{i}]")
                if type(generation) is not int: raise ContractError("INVALID_TYPE_INT", f"$.validation_run.events[{i}].recovery_generation")
            normalized.append(event)
        except ContractError as exc:
            errors.append(str(exc))
    seqs = [e["seq"] for e in normalized]
    walls = [e["wall_ms"] for e in normalized]
    if seqs != sorted(seqs) or len(seqs) != len(set(seqs)): errors.append("RECOVERY_TIMELINE_SEQ_INVALID")
    if walls != sorted(walls): errors.append("RECOVERY_TIMELINE_WALL_INVALID")

    groups = defaultdict(list)
    for event in normalized:
        if type(event.get("recovery_generation")) is int: groups[event["recovery_generation"]].append(event)
    totals = Counter()
    peer_totals = defaultdict(Counter)
    request_walls = []

    for generation, group in sorted(groups.items()):
        req = [e for e in group if e.get("type") == "RECOVERY_REQUESTED"]
        first = [e for e in group if e.get("type") == "FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY"]
        success = [e for e in group if e.get("type") == "RECOVERY_SUCCESS"]
        failure = [e for e in group if e.get("type") == "RECOVERY_FAILURE"]
        terminal = success + failure
        if not (req or first or terminal): continue
        if len(req) != 1:
            errors.append(f"RECOVERY_REQUEST_COUNT_INVALID:g{generation}")
            continue
        request_walls.append(float(req[0]["wall_ms"]))
        if len(terminal) != 1:
            errors.append(f"RECOVERY_TERMINAL_COUNT_INVALID:g{generation}")
            continue
        if success:
            if len(first) != 1: errors.append(f"RECOVERY_FIRST_VALID_COUNT_INVALID:g{generation}")
            elif not (req[0]["seq"] < first[0]["seq"] < success[0]["seq"]): errors.append(f"RECOVERY_CAUSAL_ORDER_INVALID:g{generation}")
        elif first:
            errors.append(f"FIRST_VALID_WITH_FAILURE:g{generation}")
        if first and first[0]["seq"] > terminal[0]["seq"]: errors.append(f"CALLBACK_AFTER_TERMINAL:g{generation}")

        trigger = req[0].get("trigger_kind")
        target = req[0].get("trigger_peer_id") or req[0].get("peer_id")
        if trigger == "PEER_STARVATION":
            if not isinstance(target, str) or not target:
                errors.append(f"RECOVERY_TARGET_MISSING:g{generation}")
            else:
                totals["peer_request"] += 1; peer_totals[target]["request"] += 1
                if first:
                    totals["first"] += 1; peer_totals[target]["first"] += 1
                    if first[0].get("peer_id") != target: errors.append(f"FIRST_VALID_WRONG_TARGET:g{generation}")
                if success:
                    totals["peer_success"] += 1; peer_totals[target]["success"] += 1
                    if success[0].get("peer_id") != target: errors.append(f"RECOVERY_SUCCESS_WRONG_TARGET:g{generation}")
                if failure:
                    totals["peer_failure"] += 1; peer_totals[target]["failure"] += 1

        probe_starts = [e for e in group if e.get("type") == "ACQUISITION_STRATEGY_CHANGED" and e.get("to_strategy") == "FILTERED_RECOVERY_PROBE"]
        probe_ends = [e for e in group if e.get("type") == "ACQUISITION_STRATEGY_CHANGED" and e.get("from_strategy") == "FILTERED_RECOVERY_PROBE" and e.get("to_strategy") in ("FILTERED_PRIMARY", "FAILED_SAFE")]
        if len(probe_starts) != 1:
            errors.append(f"RECOVERY_PROBE_START_INVALID:g{generation}")
        else:
            start = float(probe_starts[0]["wall_ms"])
            if probe_ends:
                if len(probe_ends) != 1: errors.append(f"RECOVERY_PROBE_END_INVALID:g{generation}")
                else:
                    duration = float(probe_ends[0]["wall_ms"]) - start
                    if duration < 0: errors.append(f"RECOVERY_PROBE_DURATION_INVALID:g{generation}")
                    if duration > 15000: errors.append(f"FILTERED_PROBE_HARD_LIMIT_EXCEEDED:g{generation}")
                    if duration > 14500: errors.append(f"FILTERED_PROBE_EXIT_TARGET_MISSED:g{generation}")
            else:
                duration = require_number(run, "ended_wall_ms", "$.validation_run") - start
                if duration > 15000: errors.append(f"FILTERED_PROBE_HARD_LIMIT_EXCEEDED:g{generation}")

    request_walls.sort()
    for start in request_walls:
        if sum(1 for t in request_walls if start <= t <= start + 300000) > 3:
            errors.append("RECOVERY_BUDGET_EXCEEDED")
            break
    return list(dict.fromkeys(errors)), totals, peer_totals

def validate_export(doc: dict, acceptance: bool = True) -> dict:
    gates = {f"G{i}": {"pass": True, "errors": []} for i in range(17)}
    def fail(gate, code):
        gates[gate]["pass"] = False
        if code not in gates[gate]["errors"]: gates[gate]["errors"].append(code)
    try:
        export, run = unwrap_export(doc)
    except ContractError as exc:
        fail("G0", str(exc)); return {"pass": False, "gates": gates, "errors": [str(exc)]}

    try:
        if require_int(run, "snapshot_schema_version", "$.validation_run") != 3: fail("G0", "SNAPSHOT_SCHEMA_DRIFT")
        if require_bool(run, "snapshot_frozen", "$.validation_run") is not True: fail("G0", "SNAPSHOT_NOT_FROZEN")
        if require_bool(export, "json_self_contained") is not True: fail("G0", "JSON_NOT_SELF_CONTAINED")
        if require_bool(export, "screenshots_required") is not False: fail("G0", "SCREENSHOTS_CONTRACT_DRIFT")
    except ContractError as exc: fail("G0", str(exc))
    try:
        if require_string(export, "build") != "0.2.0-experimental.15": fail("G1", "BUILD_MISMATCH")
        if require_int(export, "protocol_version") != 2: fail("G1", "PROTOCOL_MISMATCH")
    except ContractError as exc: fail("G1", str(exc))
    for key, wanted in (("manual_geometry_override", False), ("human_scanning_enabled", False), ("human_localization_validated", False), ("rescue_use_validated", False)):
        try:
            if require_bool(export, key) is not wanted: fail("G2", f"SAFETY_CONTRACT_DRIFT:{key}")
        except ContractError as exc: fail("G2", str(exc))
    try:
        elapsed = require_number(run, "elapsed_ms", "$.validation_run")
        eligible = require_bool(run, "acceptance_duration_eligible", "$.validation_run")
        short = require_bool(run, "short_diagnostic_run", "$.validation_run")
        if acceptance and (elapsed < 300000 or not eligible or short): fail("G3", "LONG_RUN_INELIGIBLE")
    except ContractError as exc: fail("G3", str(exc))
    try:
        pf = require_dict(run, "preflight_at_start", "$.validation_run")
        if require_bool(pf, "ready", "$.validation_run.preflight_at_start") is not True: fail("G4", "PREFLIGHT_NOT_READY")
        if require_string(pf, "acquisition_strategy", "$.validation_run.preflight_at_start") != "FILTERED_PRIMARY": fail("G4", "PREFLIGHT_STRATEGY_INVALID")
        if require_int(pf, "hardware_filter_count", "$.validation_run.preflight_at_start") <= 0: fail("G4", "PREFLIGHT_FILTER_MISSING")
    except ContractError as exc: fail("G4", str(exc))
    try:
        env = require_dict(run, "environment", "$.validation_run")
        if require_bool(env, "valid", "$.validation_run.environment") is not True: fail("G5", "ENVIRONMENT_INVALID")
        if require_int(env, "unauthorized_strategy_violation_count", "$.validation_run.environment") != 0: fail("G5", "UNAUTHORIZED_STRATEGY_VIOLATION")
        require_int(env, "violation_count", "$.validation_run.environment"); require_list(env, "violation_types", "$.validation_run.environment")
        intervals = require_list(run, "environment_violation_events", "$.validation_run")
        by_type = {}
        for i, event in enumerate(intervals):
            if not isinstance(event, dict): fail("G5", f"ENVIRONMENT_INTERVAL_INVALID:{i}"); continue
            typ = require_string(event, "type", f"$.validation_run.environment_violation_events[{i}]")
            start = require_number(event, "started_wall_ms", f"$.validation_run.environment_violation_events[{i}]")
            duration = require_number(event, "duration_ms", f"$.validation_run.environment_violation_events[{i}]")
            if duration < 0: fail("G5", f"ENVIRONMENT_INTERVAL_INVALID:{i}")
            resolved = event.get("resolved_wall_ms")
            if resolved is not None and type(resolved) not in (int, float): fail("G5", f"ENVIRONMENT_INTERVAL_RESOLVED_INVALID:{i}")
            if type(resolved) in (int, float) and abs((float(resolved)-start)-duration) > 1e-6: fail("G5", f"ENVIRONMENT_INTERVAL_DURATION_MISMATCH:{i}")
            if typ in by_type and start < by_type[typ]: fail("G5", f"ENVIRONMENT_INTERVAL_OVERLAP:{typ}")
            by_type[typ] = float(resolved) if type(resolved) in (int, float) else float("inf")
    except ContractError as exc: fail("G5", str(exc))
    try:
        if require_number(run, "usable_metric_range_uptime_percent", "$.validation_run") < 90: fail("G6", "USABLE_METRIC_UPTIME_LOW")
    except ContractError as exc: fail("G6", str(exc))
    try:
        if require_number(run, "geometry_2d_uptime_percent", "$.validation_run") < 90: fail("G7", "GEOMETRY2D_UPTIME_LOW")
    except ContractError as exc: fail("G7", str(exc))
    counters = None
    try:
        counters = require_dict(run, "validation_counters", "$.validation_run")
        if require_int(counters, "peer_expire_delta", "$.validation_run.validation_counters") != 0: fail("G8", "PEER_EXPIRE_NONZERO")
    except ContractError as exc: fail("G8", str(exc))
    try:
        acq = require_dict(run, "acquisition_state_at_end", "$.validation_run")
        if require_int(acq, "recovery_attempts_in_current_5min_window", "$.validation_run.acquisition_state_at_end") > 3: fail("G9", "RECOVERY_BUDGET_EXCEEDED")
        if require_int(acq, "filtered_probe_window_ms", "$.validation_run.acquisition_state_at_end") != 15000: fail("G13", "FILTERED_PROBE_HARD_LIMIT_DRIFT")
        if require_int(acq, "filtered_probe_exit_target_ms", "$.validation_run.acquisition_state_at_end") != 14500: fail("G13", "FILTERED_PROBE_EXIT_TARGET_DRIFT")
    except ContractError as exc: fail("G9", str(exc)); fail("G13", str(exc))
    try:
        rec_errors, totals, peer_totals = _recovery_analysis(run)
        for code in rec_errors:
            if "BUDGET" in code: fail("G9", code)
            elif "WRONG_TARGET" in code or "TARGET_MISSING" in code: fail("G11", code)
            elif "PROBE" in code: fail("G13", code)
            else: fail("G10", code)
        if counters is None: counters = require_dict(run, "validation_counters", "$.validation_run")
        expected_global = {"peer_starvation_recovery_request_delta": totals.get("peer_request",0), "recovery_first_valid_callback_delta": totals.get("first",0), "peer_starvation_recovery_success_delta": totals.get("peer_success",0), "peer_starvation_recovery_failure_delta": totals.get("peer_failure",0)}
        for key, expected in expected_global.items():
            actual = require_int(counters, key, "$.validation_run.validation_counters")
            if actual != expected: fail("G12", f"RECOVERY_COUNTER_EVENT_MISMATCH:{key}:{actual}!={expected}")
        peers = require_list(run, "per_peer_at_end", "$.validation_run")
        peer_index = {}
        for i, peer in enumerate(peers):
            if not isinstance(peer, dict): fail("G12", f"PER_PEER_INVALID:{i}"); continue
            peer_index[require_string(peer, "node_id", f"$.validation_run.per_peer_at_end[{i}]")] = peer
        for peer_id, expected in peer_totals.items():
            if peer_id not in peer_index: fail("G12", f"RECOVERY_COUNTER_PEER_MISSING:{peer_id}"); continue
            fields = {"run_starvation_recovery_participation_count": expected["request"], "run_first_callback_after_recovery_count": expected["first"], "run_starvation_recovery_success_count": expected["success"], "run_starvation_recovery_failure_count": expected["failure"]}
            for key, wanted in fields.items():
                actual = require_int(peer_index[peer_id], key, f"$.validation_run.per_peer_at_end[{peer_id}]")
                if actual != wanted: fail("G12", f"RECOVERY_COUNTER_EVENT_MISMATCH:{peer_id}:{key}:{actual}!={wanted}")
    except ContractError as exc: fail("G12", str(exc))
    try:
        meta = require_dict(export, "export_metadata")
        for key in ("device_alias","device_manufacturer","device_model","node_id","run_id","run_type","snapshot_stage","generated_at","build","suggested_filename"): require_string(meta,key,"$.export_metadata")
        require_number(meta,"elapsed_ms","$.export_metadata"); require_bool(meta,"snapshot_frozen","$.export_metadata"); require_int(meta,"export_sequence","$.export_metadata"); require_int(meta,"protocol_version","$.export_metadata")
        if meta["snapshot_stage"] not in STAGES: fail("G14","INVALID_SNAPSHOT_STAGE")
        if meta["run_type"] not in ("LONG","SHORT"): fail("G14","INVALID_RUN_TYPE")
        if meta["run_id"] != run.get("run_id"): fail("G14","EXPORT_RUN_ID_MISMATCH")
        if meta["elapsed_ms"] != run.get("elapsed_ms"): fail("G14","EXPORT_ELAPSED_MISMATCH")
        if meta["snapshot_frozen"] != run.get("snapshot_frozen"): fail("G14","EXPORT_FROZEN_MISMATCH")
        if meta["build"] != export.get("build") or meta["protocol_version"] != export.get("protocol_version"): fail("G14","EXPORT_VERSION_METADATA_MISMATCH")
        source = require_field(meta,"source_long_run_id","$.export_metadata")
        if source is not None and not isinstance(source,str): fail("G14","INVALID_SOURCE_LONG_RUN_ID")
    except ContractError as exc: fail("G14", str(exc))
    errors = [e for gate in gates.values() for e in gate["errors"]]
    return {"pass": all(g["pass"] for g in gates.values()), "gates": gates, "errors": errors}

def canonical_run(doc: dict) -> str:
    _, run = unwrap_export(doc)
    return json.dumps(run, sort_keys=True, separators=(",",":"))

def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh: return json.load(fh)
