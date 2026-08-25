#!/usr/bin/env python3
import json,sys
files=sys.argv[1:]; runs=[json.load(open(p)).get('validation_run',json.load(open(p))) for p in files]
canon=[json.dumps(r,sort_keys=True,separators=(',',':')) for r in runs]
ok=len(set(canon))==1
print(json.dumps({'files':files,'validation_run_identical':ok},indent=2)); sys.exit(0 if ok else 1)
