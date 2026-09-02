#!/usr/bin/env python3
import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
hp=(ROOT/'apps/mobile/src/humanPresence.ts').read_text()
assert "schema:'CalibrationMetaWireV2'" in hp
assert "schema:'CalibrationAckWireV2'" in hp
assert "schema:'DecisionMetaWireV2'" in hp
assert "schema:'DecisionAckWireV2'" in hp
assert 'DUPLICATE_CALIBRATION_START_IDEMPOTENT' in hp
assert "p?.session_id===authority.view.session_id" in hp
assert "p?.coordinator_id===coordinatorNodeId" in hp
assert "a.t===topology_hash" in hp and "a.d===cal.authorityDigest" in hp
assert "cohort:cal.expectedCohort" not in re.search(r"function calibrationMetaWire\(\).*?\nfunction calibrationAckWire",hp,re.S).group(0)
for n in ['calibration-wire-budget-report.json','critical-control-wire-budget-report.json','dev20.14-physical-no-go-reproduction.json','calibration-distributed-convergence-report.json','calibration-generation-idempotency-report.json','artifact-control-reorder-report.json','authority-non-regression-report.json','distributed-fault-injection-report-dev20.15.json','evidence-contract-consistency-report.json','rollback-readiness-dev20.15.json','engineering-go-dev20.15.json','g10-dev20.15.json']:
    d=json.loads((ROOT/'validation/reports'/n).read_text()); assert d
w=json.loads((ROOT/'validation/reports/critical-control-wire-budget-report.json').read_text())
assert w['pass']
for key,row in w['measurements'].items():
    assert row['payload_bytes']<600,(key,row)
    assert row['frame_bytes']<900,(key,row)
    assert row['datagram_bytes']<1200,(key,row)
r=json.loads((ROOT/'validation/reports/dev20.14-physical-no-go-reproduction.json').read_text())
assert r['calibration_meta_payload_bytes']==799 and r['attempts']==27 and r['failures']==27 and r['successes']==0
assert r['error']=='CRITICAL_CONTROL_PAYLOAD_OVER_600' and r['authority_ack']=='3/3'
g=json.loads((ROOT/'validation/reports/g10-dev20.15.json').read_text())
assert g['engineering_go'] and g['g10']=='PHYSICAL_PENDING' and not g['g10_go'] and g['g11']=='BLOCKED' and g['dev21']=='BLOCKED'
assert (ROOT/'validation/analysis/validate_dev20_15_g10.py').exists()
assert (ROOT/'TESTING_DEV20_15.md').exists()
print('dev20.15 remediation regression PASS')
