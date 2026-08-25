#!/usr/bin/env python3
import json,sys
from pathlib import Path
from dev15_validation import load_json,validate_export
failed=False
for name in sys.argv[1:]:
    result=validate_export(load_json(Path(name)),acceptance=True)
    print(json.dumps({'file':name,**result},indent=2)); failed|=not result['pass']
raise SystemExit(1 if failed else 0)
