#!/usr/bin/env python3
import argparse,json
from dev16_validation import validate_campaign
p=argparse.ArgumentParser(); p.add_argument('--evidence-dir',required=True); p.add_argument('--output',required=True); p.add_argument('--directed',action='store_true'); a=p.parse_args(); r=validate_campaign(a.evidence_dir,a.directed); open(a.output,'w').write(json.dumps({'report_version':18,'release':'dev-16',**r},indent=2)+'\n'); raise SystemExit(0 if r['pass'] else 1)
