#!/usr/bin/env python3
import json,sys
from dev14_validation import environment_errors
d=json.load(open(sys.argv[1])); e=environment_errors(d); print(json.dumps({"pass":not e,"errors":e},indent=2)); sys.exit(0 if not e else 1)
