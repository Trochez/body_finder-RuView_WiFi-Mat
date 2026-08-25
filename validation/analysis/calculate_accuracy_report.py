#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, math
from collections import defaultdict
from pathlib import Path

def norm(value: str) -> str: return "".join(ch for ch in value.lower() if ch.isalnum())
def load(path): return json.load(open(path,encoding="utf-8"))

ap=argparse.ArgumentParser(); ap.add_argument("--ground-truth",required=True); ap.add_argument("--evidence-dir",required=True); ap.add_argument("--output",default="accuracy_report.json"); args=ap.parse_args()
gt=load(args.ground_truth)
if gt.get("schema")!="body-finder-ground-truth-distances-v1" or gt.get("units")!="m" or not isinstance(gt.get("pairs_m"),list): raise SystemExit("invalid distances-only ground truth schema")
exports=[]
for path in sorted(Path(args.evidence_dir).rglob("*.json")):
    try: doc=load(path)
    except Exception: continue
    meta=doc.get("export_metadata")
    if isinstance(meta,dict) and meta.get("snapshot_stage")=="LONG_1" and isinstance(doc.get("validation_run"),dict): exports.append(doc)
aliases={}
for doc in exports:
    meta=doc["export_metadata"]; node_id=meta.get("node_id")
    if not isinstance(node_id,str): continue
    for candidate in (meta.get("device_alias"),meta.get("device_model"),node_id):
        if isinstance(candidate,str): aliases[norm(candidate)]=node_id
observed=defaultdict(list)
for doc in exports:
    run=doc["validation_run"]; observations=run.get("fused_range_observations_at_end",doc.get("fused_range_observations",[]))
    if not isinstance(observations,list): continue
    for item in observations:
        if not isinstance(item,dict): continue
        a,b,distance=item.get("observer_node_id"),item.get("peer_node_id"),item.get("distance_m")
        if isinstance(a,str) and isinstance(b,str) and type(distance) in (int,float): observed[tuple(sorted((a,b)))].append(float(distance))
pairs=[]; errors=[]
for item in gt["pairs_m"]:
    if not isinstance(item,dict) or not isinstance(item.get("a"),str) or not isinstance(item.get("b"),str) or type(item.get("distance_m")) not in (int,float): raise SystemExit("invalid pairs_m entry")
    aid,bid=aliases.get(norm(item["a"])),aliases.get(norm(item["b"]))
    if not aid or not bid: raise SystemExit(f"cannot resolve aliases: {item['a']} / {item['b']}")
    values=observed.get(tuple(sorted((aid,bid))),[])
    if not values: raise SystemExit(f"no observed range for {item['a']} / {item['b']}")
    mean=sum(values)/len(values); truth=float(item["distance_m"]); error=mean-truth; errors.append(error)
    pairs.append({"a":item["a"],"b":item["b"],"sample_count":len(values),"observed_mean_m":mean,"ground_truth_m":truth,"signed_error_m":error,"absolute_error_m":abs(error)})
out={"release":"dev-15","confidence":"COARSE","informational_only":True,"automatic_calibration_change_allowed":False,"pair_count":len(pairs),"pairs":pairs,"mae_m":sum(abs(x) for x in errors)/len(errors) if errors else None,"rmse_m":math.sqrt(sum(x*x for x in errors)/len(errors)) if errors else None,"maximum_absolute_error_m":max((abs(x) for x in errors),default=None)}
Path(args.output).write_text(json.dumps(out,indent=2)+"\n"); print(json.dumps(out,indent=2))
