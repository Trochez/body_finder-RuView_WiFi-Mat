#!/usr/bin/env python3
import argparse
import json
import pathlib
import sys

EXPECTED_BUILD = "0.2.0-experimental.19"
EXPECTED_PROTOCOL = 2
EXPECTED_SCHEMA = 4
MIN_ELAPSED_MS = 330_000


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_run(doc):
    run = doc.get("validation_run")
    if not isinstance(run, dict):
        raise ValueError("validation_run missing")
    return run


def gate(name, ok, observed=None, expected=None):
    return {"gate": name, "pass": bool(ok), "observed": observed, "expected": expected}


def strict_dev19(path):
    doc = load(path)
    run = get_run(doc)
    pre = run.get("preflight_at_start") or {}
    expected_ids = run.get("expected_peer_ids_at_start") or pre.get("expected_ble_peer_ids") or []
    expected_count = run.get("expected_peer_count_at_start", pre.get("expected_ble_peer_count"))
    env = run.get("environment") or {}
    acquisition = run.get("acquisition_state_at_end") or {}
    timing = run.get("recovery_timing_summary") or {}
    fabric = run.get("fabric_event_timeline") or {}
    fabric_events = fabric.get("events") or []
    fabric_total = fabric.get("total_count", len(fabric_events))
    fabric_truncated = bool(fabric.get("truncated", False))
    expired_events = sum(1 for e in fabric_events if e.get("type") == "PEER_EXPIRED")
    hard_breaches = int(timing.get("unfiltered_hard_limit_breach_count", 0) or 0) + int(timing.get("filtered_probe_hard_limit_breach_count", 0) or 0)
    rolling = acquisition.get("recovery_attempts_max_in_any_rolling_5min_window", 0)
    environment_valid = bool(run.get("environment_valid", env.get("valid", False)))
    violation_count = int(run.get("environment_violation_count", env.get("violation_count", 0)) or 0)
    active_generation = acquisition.get("active_recovery_generation")
    logical_strategy = acquisition.get("logical_acquisition_strategy") or run.get("acquisition_strategy")

    gates = [
        gate("G0_BUILD", doc.get("build") == EXPECTED_BUILD, doc.get("build"), EXPECTED_BUILD),
        gate("G0_PROTOCOL", doc.get("protocol_version") == EXPECTED_PROTOCOL, doc.get("protocol_version"), EXPECTED_PROTOCOL),
        gate("G0_JSON_SELF_CONTAINED", doc.get("json_self_contained") is True, doc.get("json_self_contained"), True),
        gate("G0_NO_SCREENSHOTS", doc.get("screenshots_required") is False, doc.get("screenshots_required"), False),
        gate("G0_SNAPSHOT", run.get("snapshot_frozen") is True and run.get("snapshot_schema_version") == EXPECTED_SCHEMA, {"frozen":run.get("snapshot_frozen"),"schema":run.get("snapshot_schema_version")}, {"frozen":True,"schema":EXPECTED_SCHEMA}),
        gate("G1_FROZEN_COHORT_COUNT", expected_count == 2, expected_count, 2),
        gate("G1_FROZEN_COHORT_IDS", isinstance(expected_ids, list) and len(set(expected_ids)) == 2, expected_ids, "2 unique peer IDs"),
        gate("G2_ENVIRONMENT", environment_valid and violation_count == 0, {"valid":environment_valid,"violation_count":violation_count}, {"valid":True,"violation_count":0}),
        gate("G3_DURATION", int(run.get("elapsed_ms", 0) or 0) >= MIN_ELAPSED_MS, run.get("elapsed_ms"), f">={MIN_ELAPSED_MS}"),
        gate("G4_PEER_EXPIRE", int(run.get("peer_expire_delta", -1) or 0) == 0, run.get("peer_expire_delta"), 0),
        gate("G5_METRIC_UPTIME", float(run.get("usable_metric_range_uptime_percent", 0) or 0) >= 90.0, run.get("usable_metric_range_uptime_percent"), ">=90"),
        gate("G6_GEOMETRY_2D", float(run.get("geometry_2d_uptime_percent", 0) or 0) >= 90.0, run.get("geometry_2d_uptime_percent"), ">=90"),
        gate("G7_RECOVERY_BUDGET", int(rolling or 0) <= 3, rolling, "<=3/rolling 300000ms"),
        gate("G8_TIMING_HARD_BREACH", hard_breaches == 0, hard_breaches, 0),
        gate("G9_END_STRATEGY", logical_strategy == "FILTERED_PRIMARY" and active_generation in (None, "", "null"), {"strategy":logical_strategy,"active_recovery_generation":active_generation}, {"strategy":"FILTERED_PRIMARY","active_recovery_generation":None}),
        gate("G10_FABRIC_TIMELINE_PRESENT", isinstance(fabric, dict) and "events" in fabric and "total_count" in fabric and "truncated" in fabric, {"keys":sorted(fabric.keys()) if isinstance(fabric,dict) else []}, "events,total_count,truncated"),
        gate("G10_FABRIC_TIMELINE_COUNT", fabric_truncated or fabric_total == len(fabric_events), {"total_count":fabric_total,"events":len(fabric_events),"truncated":fabric_truncated}, "equal unless truncated"),
        gate("G10_EXPIRE_RECONSTRUCTION", expired_events == int(run.get("peer_expire_delta", 0) or 0), {"expired_events":expired_events,"peer_expire_delta":run.get("peer_expire_delta")}, "equal"),
        gate("G10_COHORT_MATCH", fabric.get("expected_peer_count_at_start") == expected_count and sorted(fabric.get("expected_peer_ids_at_start") or []) == sorted(expected_ids), {"fabric_count":fabric.get("expected_peer_count_at_start"),"run_count":expected_count,"fabric_ids":fabric.get("expected_peer_ids_at_start"),"run_ids":expected_ids}, "equal"),
        gate("G11_HUMAN_FLAGS", doc.get("human_scanning_enabled") is False and doc.get("human_localization_validated") is False and doc.get("rescue_use_validated") is False, {"human_scanning_enabled":doc.get("human_scanning_enabled"),"human_localization_validated":doc.get("human_localization_validated"),"rescue_use_validated":doc.get("rescue_use_validated")}, "all false"),
    ]
    return {
        "schema_version": 1,
        "validator": "validate_dev19_session.py",
        "source": str(path),
        "device_alias": (doc.get("export_metadata") or {}).get("device_alias"),
        "run_id": run.get("run_id"),
        "pass": all(g["pass"] for g in gates),
        "gates": gates,
    }


def historical_dev18(path):
    doc = load(path)
    run = get_run(doc)
    env_valid = bool(run.get("environment_valid", False))
    peer_expire = int(run.get("peer_expire_delta", 0) or 0)
    usable = float(run.get("usable_metric_range_uptime_percent", run.get("metric_range_uptime_percent", 0)) or 0)
    geometry = float(run.get("geometry_2d_uptime_percent", 0) or 0)
    elapsed = int(run.get("elapsed_ms", 0) or 0)
    ok = env_valid and peer_expire == 0 and usable >= 90 and geometry >= 90 and elapsed >= 300_000
    return {"source":str(path),"pass":ok,"environment_valid":env_valid,"peer_expire_delta":peer_expire,"usable_metric_range_uptime_percent":usable,"geometry_2d_uptime_percent":geometry,"elapsed_ms":elapsed}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--output")
    ap.add_argument("--historical-dev18", action="store_true")
    ap.add_argument("--expect-historical-pattern", action="store_true", help="Require exactly two PASS and one FAIL; FAIL must be Pixel10-like peer expiry")
    args = ap.parse_args()
    results = [historical_dev18(p) if args.historical_dev18 else strict_dev19(p) for p in args.inputs]
    if args.historical_dev18 and args.expect_historical_pattern:
        passes = sum(1 for r in results if r["pass"])
        fails = [r for r in results if not r["pass"]]
        overall = passes == 2 and len(fails) == 1 and fails[0].get("peer_expire_delta",0) > 0
    else:
        overall = all(r["pass"] for r in results)
    report = {"schema_version":1,"mode":"historical-dev18" if args.historical_dev18 else "dev19-strict","pass":overall,"results":results}
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        pathlib.Path(args.output).write_text(text)
    print(text, end="")
    raise SystemExit(0 if overall else 1)

if __name__ == "__main__":
    main()
