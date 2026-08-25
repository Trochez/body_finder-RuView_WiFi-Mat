#!/usr/bin/env python3
import argparse,json,sys
from dev14_validation import hard_gate_errors
a=argparse.ArgumentParser(); a.add_argument("files",nargs="+"); a.add_argument("--allow-short",action="store_true"); x=a.parse_args(); out={}; ok=True
for f in x.files:
 d=json.load(open(f)); e=hard_gate_errors(d,not x.allow_short); out[f]={"pass":not e,"errors":e}; ok &= not e
print(json.dumps({"pass":ok,"files":out},indent=2)); sys.exit(0 if ok else 1)
