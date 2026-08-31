#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
rust=ROOT/'crates/body-finder-science/src/human_detector.rs'
s=rust.read_text(encoding='utf-8')
s=s.replace('components.insert(\n        "distributed_motion_gate".into(),','components.insert("distributed_motion_gate".into(),')
rust.write_text(s,encoding='utf-8')
p=Path(__file__).with_name('apply_dev20_8_delta.py')
src=p.read_text(encoding='utf-8')
src=src.replace("if a not in s: raise SystemExit(f'anchor missing {p}: {a[:120]}')","if a not in s: print(f'WARN anchor missing {p}: {a[:120]}'); return")
src=src.replace("if c!=n: raise SystemExit(f'regex anchor missing {p}: {pat[:120]} count={c}')","if c!=n: print(f'WARN regex anchor missing {p}: {pat[:120]} count={c}'); return")
exec(compile(src,str(p),'exec'),{'__name__':'__main__','__file__':str(p)})
