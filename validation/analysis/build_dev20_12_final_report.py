#!/usr/bin/env python3
import argparse,json,pathlib
ap=argparse.ArgumentParser();ap.add_argument('--g10');ap.add_argument('--g11');ap.add_argument('--release-verification');ap.add_argument('--output',default='dev20.12-final-report.json');a=ap.parse_args()
def load(p):return json.loads(pathlib.Path(p).read_text()) if p and pathlib.Path(p).exists() else {}
g10,g11,rv=load(a.g10),load(a.g11),load(a.release_verification);go=bool(g10.get('g10_go') and g11.get('g11_go') and rv.get('release_redownload_sha_verified'));o={'release':'dev-20.12','G10':'GO' if g10.get('g10_go') else 'PENDING_OR_NO_GO','G11':'GO' if g11.get('g11_go') else 'BLOCKED_OR_PENDING','G12':'GO' if go else 'PENDING','final_go':go,'dev21_blocked':not go};pathlib.Path(a.output).write_text(json.dumps(o,indent=2)+'\n');print(json.dumps(o,indent=2))
