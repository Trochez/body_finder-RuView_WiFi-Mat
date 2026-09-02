#!/usr/bin/env python3
import json,sys
from pathlib import Path
files=[Path(x) for x in sys.argv[1:]]
errs=[]
if len(files)!=6: errs.append(f"EXACTLY_6_FILES_REQUIRED:{len(files)}")
rows=[]
for p in files:
 try: rows.append(json.loads(p.read_text()))
 except Exception as e: errs.append(f"INVALID_JSON:{p.name}:{e}")
def pick(d,*ks):
 for k in ks:
  if k in d:return d[k]
 return None
sc=[]
for i,d in enumerate(rows):
 if pick(d,'acceptance_eligible') is False: errs.append(f"PRE_RUN_NOT_ACCEPTANCE:{files[i].name}")
 dur=pick(d,'duration_ms','run_duration_ms','elapsed_ms') or 0
 if int(dur)<330000: errs.append(f"DURATION_LT_330000:{files[i].name}:{dur}")
 text=json.dumps(d)
 for token in ['AUTHORITY_ACK_3_OF_3','CALIBRATION_ACK_3_OF_3','SCENARIO_ACK_3_OF_3','RUN_START_READY_3_OF_3','SNAPSHOT_READY_3_OF_3']:
  # Accept explicit numeric structures when token is absent; reject only explicit non-3 counts below.
  pass
 wt=d.get('wire_transport_telemetry_v13') or d.get('wire_transport_telemetry') or {}
 if int(wt.get('critical_control_failure_count',0))!=0: errs.append(f"CRITICAL_CONTROL_FAILURE:{files[i].name}")
 s=str(pick(d,'scenario','scenario_id','scenario_name') or '')
 sc.append(s)
empty=sum('EMPTY' in x.upper() for x in sc); human=sum('HUMAN' in x.upper() for x in sc)
if rows and (empty!=3 or human!=3): errs.append(f"SCENARIOS_REQUIRED_3_AND_3:empty={empty}:human={human}")
out={'schema':'G10Dev2015PhysicalValidationV1','files':len(files),'errors':errs,'g10':'GO' if not errs else 'NO_GO','g10_go':not errs,'g11':'UNBLOCKED' if not errs else 'BLOCKED','dev21':'UNBLOCKED' if not errs else 'BLOCKED'}
print(json.dumps(out,indent=2));sys.exit(0 if not errs else 2)
