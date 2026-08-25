#!/usr/bin/env python3
import argparse,json,sys
from pathlib import Path
from build_acceptance_report import build

ap=argparse.ArgumentParser(); ap.add_argument('--pixel10'); ap.add_argument('--pixel7'); ap.add_argument('--lenovo'); ap.add_argument('--evidence-dir'); ap.add_argument('--output',default='-'); a=ap.parse_args()
if a.evidence_dir:
    directory=Path(a.evidence_dir)
else:
    supplied=[Path(x) for x in (a.pixel10,a.pixel7,a.lenovo) if x]
    if len(supplied)!=3: ap.error('provide --evidence-dir or all of --pixel10/--pixel7/--lenovo')
    parents={p.resolve().parent for p in supplied}
    if len(parents)!=1: ap.error('the three long-1 exports must share a directory containing sibling stages')
    directory=parents.pop()
result=build(directory); text=json.dumps(result,indent=2)+'\n'
if a.output=='-': sys.stdout.write(text)
else: Path(a.output).write_text(text)
raise SystemExit(0 if result['pass'] else 1)
