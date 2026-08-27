#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,pathlib,sys
from body_finder_v1_science import aggregate_v1_reports

def main()->int:
    ap=argparse.ArgumentParser()
    for k in ('dev19','dev20','dev21','dev22','dev23','dev24'): ap.add_argument('--'+k,required=True)
    ap.add_argument('--output',required=True); a=ap.parse_args(); reports={k:json.loads(pathlib.Path(getattr(a,k)).read_text()) for k in ('dev19','dev20','dev21','dev22','dev23','dev24')}
    out=aggregate_v1_reports(reports); pathlib.Path(a.output).write_text(json.dumps(out,indent=2)+'\n'); print(json.dumps(out,indent=2)); return 0 if out['final_go'] else 2
if __name__=='__main__':sys.exit(main())
