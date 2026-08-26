#!/usr/bin/env python3
import argparse,json
from dev16_validation import validate_campaign
p=argparse.ArgumentParser(); p.add_argument('--evidence-dir',required=True); p.add_argument('--output',required=True); a=p.parse_args(); r=validate_campaign(a.evidence_dir,True); open(a.output,'w').write(json.dumps(r,indent=2)+'\n'); raise SystemExit(0 if r['pass'] else 1)
