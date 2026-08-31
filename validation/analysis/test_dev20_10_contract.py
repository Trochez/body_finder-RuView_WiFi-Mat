#!/usr/bin/env python3
import pathlib,tempfile,shutil,subprocess,json,sys
R=pathlib.Path(__file__).resolve().parents[2];F=R/'validation/fixtures/dev20_10';V=R/'validation/analysis/validate_dev20_10_smoke.py'
def run(d):return subprocess.run([sys.executable,str(V),'--evidence-dir',str(d),'--output',str(d/'verdict.json')],capture_output=True).returncode
with tempfile.TemporaryDirectory() as x:
 d=pathlib.Path(x)
 for f in F.glob('go-*.json'):shutil.copy(f,d/f.name)
 assert run(d)==0
 t=next(d.glob('*human.json'));o=json.loads(t.read_text());o['scenario']='SMOKE_CAL_EMPTY';t.write_text(json.dumps(o));assert run(d)!=0
print('dev20.10 contract self-test PASS')
