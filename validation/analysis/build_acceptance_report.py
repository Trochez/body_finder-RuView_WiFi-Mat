#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from dev15_validation import canonical_run, load_json, validate_export

STAGES = ("LONG_1", "LONG_2", "SHORT", "LONG_POST_SHORT")

def discover(directory: Path):
    found = {}
    for path in sorted(directory.rglob("*.json")):
        try: doc = load_json(path)
        except Exception: continue
        meta = doc.get("export_metadata")
        if not isinstance(meta, dict): continue
        alias, stage = meta.get("device_alias"), meta.get("snapshot_stage")
        if not isinstance(alias, str) or stage not in STAGES: continue
        if stage in found.setdefault(alias, {}):
            raise SystemExit(f"duplicate stage {alias}/{stage}: {found[alias][stage][0]} and {path}")
        found[alias][stage] = (path, doc)
    return found

def build(evidence_dir: Path):
    devices = discover(evidence_dir)
    gates = {f"G{i}": {"pass": True, "errors": []} for i in range(17)}
    output_devices = {}
    def fail(gate, code):
        gates[gate]["pass"] = False
        if code not in gates[gate]["errors"]: gates[gate]["errors"].append(code)
    if len(devices) < 3: fail("G14", f"EXPECTED_AT_LEAST_3_DEVICES:{len(devices)}")
    for alias, stages in sorted(devices.items()):
        missing = [s for s in STAGES if s not in stages]
        dres = {"pass": True, "stages": {k: str(v[0]) for k,v in stages.items()}, "errors": []}
        if missing:
            dres["pass"] = False; dres["errors"].append("MISSING_STAGES:" + ",".join(missing))
            fail("G15", f"{alias}:MISSING_HISTORY_EVIDENCE"); fail("G16", f"{alias}:MISSING_SHORT_EVIDENCE")
            output_devices[alias] = dres; continue
        long1 = stages["LONG_1"][1]
        validation = validate_export(long1, acceptance=True)
        dres["long_1_validation"] = validation
        for gate, result in validation["gates"].items():
            if gate in ("G15","G16"): continue
            if not result["pass"]:
                for error in result["errors"]: fail(gate, f"{alias}:{error}")
        run1 = canonical_run(long1)
        if canonical_run(stages["LONG_2"][1]) != run1:
            fail("G15", f"{alias}:LONG_1_LONG_2_DRIFT"); dres["errors"].append("LONG_1_LONG_2_DRIFT")
        if canonical_run(stages["LONG_POST_SHORT"][1]) != run1:
            fail("G15", f"{alias}:LONG_POST_SHORT_DRIFT"); dres["errors"].append("LONG_POST_SHORT_DRIFT")
        long_id = long1["validation_run"]["run_id"]
        for stage in ("LONG_2","LONG_POST_SHORT"):
            if stages[stage][1]["validation_run"].get("run_id") != long_id: fail("G15", f"{alias}:{stage}_RUN_ID_DRIFT")
        short = stages["SHORT"][1]; short_run = short.get("validation_run",{}); short_meta = short.get("export_metadata",{})
        if short_run.get("run_id") == long_id:
            fail("G16", f"{alias}:SHORT_REPLACED_LONG"); dres["errors"].append("SHORT_REPLACED_LONG")
        if short_run.get("short_diagnostic_run") is not True or short_run.get("acceptance_duration_eligible") is not False: fail("G16", f"{alias}:SHORT_ELIGIBILITY_INVALID")
        if short_meta.get("run_type") != "SHORT" or short_meta.get("source_long_run_id") != long_id: fail("G16", f"{alias}:SHORT_METADATA_INVALID")
        if stages["LONG_POST_SHORT"][1].get("export_metadata",{}).get("source_long_run_id") != long_id: fail("G15", f"{alias}:LONG_POST_SHORT_SOURCE_INVALID")
        dres["pass"] = validation["pass"] and not dres["errors"]
        output_devices[alias] = dres
    overall = all(g["pass"] for g in gates.values()) and all(d["pass"] for d in output_devices.values())
    return {"release":"dev-15","version":"0.2.0-experimental.15","pass":overall,"screenshots_required":False,"gates":gates,"devices":output_devices}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--evidence-dir",default="."); ap.add_argument("--output",default="acceptance_report.json"); ap.add_argument("--md",default=None); args=ap.parse_args()
    result=build(Path(args.evidence_dir)); Path(args.output).write_text(json.dumps(result,indent=2)+"\n")
    md=Path(args.md or str(Path(args.output).with_suffix(".md")))
    lines=["# dev-15 acceptance report","",f"Overall: **{'PASS' if result['pass'] else 'FAIL'}**","","| Gate | Result |","|---|---|"]+[f"| {g} | {'PASS' if v['pass'] else 'FAIL'} |" for g,v in result["gates"].items()]+["","Evidence is JSON/JSONL-based; screenshots are not required."]
    md.write_text("\n".join(lines)+"\n"); print(json.dumps(result,indent=2)); return 0 if result["pass"] else 1
if __name__=="__main__": raise SystemExit(main())
