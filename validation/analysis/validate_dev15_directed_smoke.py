#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
from dev15_validation import canonical_run, load_json, validate_export

STAGES = ("LONG_1", "LONG_2", "SHORT", "LONG_POST_SHORT")
ALLOWED_LONG_GATE_FAILURES = {"G6", "G7"}  # two nodes only provide one remote peer and 1D geometry

def discover(directory: Path):
    found = {}
    for path in sorted(directory.rglob("*.json")):
        try:
            doc = load_json(path)
        except Exception:
            continue
        meta = doc.get("export_metadata")
        if not isinstance(meta, dict):
            continue
        alias, stage = meta.get("device_alias"), meta.get("snapshot_stage")
        if not isinstance(alias, str) or stage not in STAGES:
            continue
        if stage in found.setdefault(alias, {}):
            raise SystemExit(f"duplicate stage {alias}/{stage}")
        found[alias][stage] = doc
    return found

def validate(directory: Path):
    devices = discover(directory)
    errors = []
    details = {}
    if len(devices) != 2:
        errors.append(f"EXPECTED_EXACTLY_2_DEVICES:{len(devices)}")
    for alias, stages in sorted(devices.items()):
        derrors = []
        missing = [s for s in STAGES if s not in stages]
        if missing:
            derrors.append("MISSING_STAGES:" + ",".join(missing))
            details[alias] = {"pass": False, "errors": derrors}
            errors.extend(f"{alias}:{e}" for e in derrors)
            continue
        long1, long2, short, post = (stages[s] for s in STAGES)
        long_result = validate_export(long1, acceptance=True)
        for gate, result in long_result["gates"].items():
            if gate in ALLOWED_LONG_GATE_FAILURES:
                continue
            if not result["pass"]:
                derrors.extend(f"{gate}:{e}" for e in result["errors"])
        run1 = long1.get("validation_run", {})
        preflight = run1.get("preflight_at_start", {})
        if preflight.get("ready") is not True:
            derrors.append("PREFLIGHT_NOT_READY")
        if preflight.get("expected_ble_peer_count", preflight.get("expected_ble_peers")) != 1:
            derrors.append("EXPECTED_REMOTE_PEER_COUNT_NOT_1")
        if canonical_run(long2) != canonical_run(long1):
            derrors.append("LONG_1_LONG_2_DRIFT")
        if canonical_run(post) != canonical_run(long1):
            derrors.append("LONG_POST_SHORT_DRIFT")
        long_id = run1.get("run_id")
        short_run = short.get("validation_run", {})
        if short_run.get("run_id") == long_id:
            derrors.append("SHORT_REPLACED_LONG")
        if short_run.get("short_diagnostic_run") is not True:
            derrors.append("SHORT_FLAG_INVALID")
        if short.get("export_metadata", {}).get("source_long_run_id") != long_id:
            derrors.append("SHORT_SOURCE_LONG_INVALID")
        events = run1.get("events", [])
        req = [e for e in events if isinstance(e, dict) and e.get("type") == "RECOVERY_REQUESTED" and e.get("trigger_kind") == "PEER_STARVATION"]
        first = [e for e in events if isinstance(e, dict) and e.get("type") == "FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY"]
        success = [e for e in events if isinstance(e, dict) and e.get("type") == "RECOVERY_SUCCESS"]
        if not req:
            derrors.append("NO_PEER_STARVATION_RECOVERY_REQUEST")
        if not first:
            derrors.append("NO_FIRST_VALID_AFTER_RECOVERY")
        if not success:
            derrors.append("NO_RECOVERY_SUCCESS")
        details[alias] = {"pass": not derrors, "errors": derrors}
        errors.extend(f"{alias}:{e}" for e in derrors)
    return {
        "release": "dev-15",
        "mode": "DIRECTED_TWO_DEVICE_SMOKE",
        "pass": not errors,
        "screenshots_required": False,
        "full_acceptance_equivalent": False,
        "ignored_full_campaign_gates": ["G6", "G7"],
        "errors": errors,
        "devices": details,
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence-dir", required=True)
    ap.add_argument("--output", default="directed_smoke_report.json")
    args = ap.parse_args()
    result = validate(Path(args.evidence_dir))
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["pass"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
