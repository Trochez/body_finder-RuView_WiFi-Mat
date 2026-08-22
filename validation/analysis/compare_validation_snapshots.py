#!/usr/bin/env python3
import json,sys
if len(sys.argv)!=3: raise SystemExit("usage: compare_validation_snapshots.py export1.json export2.json")
a=json.load(open(sys.argv[1],encoding="utf-8")).get("validation_run"); b=json.load(open(sys.argv[2],encoding="utf-8")).get("validation_run")
if not a or not b: raise SystemExit("FAIL: validation_run missing")
if not a.get("snapshot_frozen") or not b.get("snapshot_frozen"): raise SystemExit("FAIL: snapshot_frozen must be true")
if a!=b:
  keys=sorted(set(a or {})|set(b or {})); dif=[k for k in keys if a.get(k)!=b.get(k)]
  raise SystemExit("FAIL: completed validation snapshot drift: "+", ".join(dif))
print("PASS: completed validation snapshot is immutable")
