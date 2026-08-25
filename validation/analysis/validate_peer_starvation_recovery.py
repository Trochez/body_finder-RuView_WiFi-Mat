#!/usr/bin/env python3
import json,sys
from dev14_validation import timeline_errors
d=json.load(open(sys.argv[1])); e=[x for x in timeline_errors(d) if x in {"FIRST_VALID_WRONG_TARGET","RECOVERY_SUCCESS_WITHOUT_FIRST_VALID","DUPLICATE_FIRST_VALID","DUPLICATE_TERMINAL","TERMINAL_CONTRADICTION","CALLBACK_AFTER_TERMINAL","RECOVERY_CAUSAL_ORDER_INVALID"}]; print(json.dumps({"pass":not e,"errors":e},indent=2)); sys.exit(0 if not e else 1)
