#!/usr/bin/env python3
from __future__ import annotations
import json,subprocess,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
if (HERE/'validation/fixtures/dev15/campaign').is_dir():
    ROOT=HERE; FIX=HERE/'validation/fixtures/dev15'
else:
    ROOT=HERE.parents[1]; FIX=ROOT/'validation/fixtures/dev15'
sys.path.insert(0,str(HERE))
from dev15_validation import load_json,validate_export
C=FIX/'campaign'; X=FIX/'corrupted'
def run(*cmd):
    print('+',*map(str,cmd)); subprocess.run([str(x) for x in cmd],cwd=ROOT,check=True)
with tempfile.TemporaryDirectory() as td:
    temp=Path(td)
    run(sys.executable,HERE/'build_acceptance_report.py','--evidence-dir',C,'--output',temp/'acceptance_report.json')
    report=json.load(open(temp/'acceptance_report.json')); assert report['pass'] and all(v['pass'] for v in report['gates'].values())
    run(sys.executable,HERE/'calculate_accuracy_report.py','--ground-truth',C/'ground-truth.json','--evidence-dir',C,'--output',temp/'accuracy_report.json')
    accuracy=json.load(open(temp/'accuracy_report.json')); assert accuracy['pair_count']==3 and accuracy['informational_only'] is True and accuracy['automatic_calibration_change_allowed'] is False
for path in X.glob('*.json'):
    doc=load_json(path); expected=doc['expected_error']; result=validate_export(doc,True)
    assert not result['pass'],path
    assert any(expected in error for error in result['errors']),(path,expected,result['errors'])
print('DEV15_TOOLING_MATRIX_PASS')
